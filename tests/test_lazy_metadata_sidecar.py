"""Sidecar-aware lazy_metadata behaviour.

When a skill directory contains a `parameters.yaml` sidecar, LazySkillMetadata
must read the runtime contract (allowed_extra_flags, param_hints, domain,
script, trigger_keywords, legacy_aliases, saves_h5ad, requires_preprocessed)
from the sidecar — NOT from the legacy `metadata.omicsclaw` block in the
SKILL.md frontmatter.

The skill-identity fields `name` and `description` always come from the
SKILL.md frontmatter, regardless of whether a sidecar exists.

These tests intentionally use small fabricated skill directories so they pin
behaviour, not the contents of any production skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from omicsclaw.core.lazy_metadata import LazySkillMetadata


def _write_skill(
    base: Path,
    *,
    frontmatter: dict,
    sidecar: dict | None,
    body: str = "# Test Skill\n",
) -> Path:
    """Write a fabricated skill at `base` with the given frontmatter and
    optional sidecar.  Returns the skill directory path."""
    base.mkdir(parents=True, exist_ok=True)
    skill_md = base / "SKILL.md"
    skill_md.write_text(
        "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n" + body,
        encoding="utf-8",
    )
    if sidecar is not None:
        (base / "parameters.yaml").write_text(
            yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8"
        )
    return base


def test_sidecar_supplies_allowed_extra_flags(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path / "demo-skill",
        frontmatter={"name": "demo-skill", "description": "Load when demo."},
        sidecar={
            "domain": "demo",
            "script": "demo_skill.py",
            "saves_h5ad": False,
            "requires_preprocessed": False,
            "trigger_keywords": [],
            "legacy_aliases": [],
            "allowed_extra_flags": ["--alpha", "--beta"],
            "param_hints": {},
        },
    )

    lazy = LazySkillMetadata(skill)

    assert lazy.allowed_extra_flags == {"--alpha", "--beta"}


def test_sidecar_supplies_param_hints(tmp_path: Path) -> None:
    sidecar = {
        "domain": "demo",
        "script": "demo_skill.py",
        "saves_h5ad": False,
        "requires_preprocessed": False,
        "trigger_keywords": [],
        "legacy_aliases": [],
        "allowed_extra_flags": [],
        "param_hints": {
            "wilcoxon": {
                "priority": "groupby -> corr",
                "params": ["groupby", "n_top_genes"],
                "defaults": {"groupby": "leiden", "n_top_genes": 10},
                "requires": ["obs.groupby"],
                "tips": ["Use leiden by default"],
            }
        },
    }
    skill = _write_skill(
        tmp_path / "demo-skill",
        frontmatter={"name": "demo-skill", "description": "Load when demo."},
        sidecar=sidecar,
    )

    lazy = LazySkillMetadata(skill)

    assert lazy.param_hints == sidecar["param_hints"]


def test_sidecar_overrides_legacy_omicsclaw_block(tmp_path: Path) -> None:
    """If both sidecar and legacy frontmatter block exist, sidecar wins.

    No merging — sidecar is the single source of truth for the runtime contract.
    """
    skill = _write_skill(
        tmp_path / "demo-skill",
        frontmatter={
            "name": "demo-skill",
            "description": "Load when demo.",
            "metadata": {
                "omicsclaw": {
                    "domain": "STALE",
                    "allowed_extra_flags": ["--stale"],
                    "param_hints": {"stale": {"params": ["stale"], "defaults": {}}},
                }
            },
        },
        sidecar={
            "domain": "fresh",
            "script": "demo_skill.py",
            "saves_h5ad": False,
            "requires_preprocessed": False,
            "trigger_keywords": [],
            "legacy_aliases": [],
            "allowed_extra_flags": ["--fresh"],
            "param_hints": {},
        },
    )

    lazy = LazySkillMetadata(skill)

    assert lazy.domain == "fresh"
    assert lazy.allowed_extra_flags == {"--fresh"}
    assert lazy.param_hints == {}


def test_name_and_description_always_from_frontmatter(tmp_path: Path) -> None:
    """Identity fields are not in the sidecar — they live in SKILL.md."""
    skill = _write_skill(
        tmp_path / "demo-skill",
        frontmatter={
            "name": "demo-skill",
            "description": "Load when the user wants a demo.",
        },
        sidecar={
            "domain": "demo",
            "script": "demo_skill.py",
            "saves_h5ad": False,
            "requires_preprocessed": False,
            "trigger_keywords": [],
            "legacy_aliases": [],
            "allowed_extra_flags": [],
            "param_hints": {},
        },
    )

    lazy = LazySkillMetadata(skill)

    assert lazy.name == "demo-skill"
    assert lazy.description == "Load when the user wants a demo."


def test_partial_sidecar_falls_back_per_field_to_frontmatter(tmp_path: Path) -> None:
    """If parameters.yaml exists but omits a field, lazy_metadata must fall
    back to the legacy `metadata.omicsclaw` block for THAT field, not silently
    return the empty default.  This is the realistic mid-migration shape."""
    skill = _write_skill(
        tmp_path / "demo-skill",
        frontmatter={
            "name": "demo-skill",
            "description": "Load when demo.",
            "metadata": {
                "omicsclaw": {
                    "domain": "from-frontmatter",
                    "allowed_extra_flags": ["--legacy-flag"],
                    "trigger_keywords": ["legacy", "kw"],
                    "param_hints": {"m": {"params": ["x"], "defaults": {"x": 1}}},
                    "saves_h5ad": True,
                }
            },
        },
        sidecar={
            # Sidecar covers ONLY the bookkeeping fields; runtime/lookup fields
            # absent here must come from the legacy block above.
            "domain": "from-sidecar",
            "script": "demo.py",
            "requires_preprocessed": False,
            "legacy_aliases": [],
        },
    )

    lazy = LazySkillMetadata(skill)

    # Sidecar wins where it speaks.
    assert lazy.domain == "from-sidecar"
    assert lazy.script == "demo.py"
    # Frontmatter fills the gaps the sidecar left.
    assert lazy.allowed_extra_flags == {"--legacy-flag"}
    assert lazy.trigger_keywords == ["legacy", "kw"]
    assert lazy.param_hints == {"m": {"params": ["x"], "defaults": {"x": 1}}}
    assert lazy.saves_h5ad is True


def test_null_sidecar_collection_fields_do_not_crash(tmp_path: Path) -> None:
    """A bare `field:` key in YAML parses to None.  lazy_metadata must
    coerce None -> default for collection fields so callers like
    `set(lazy.allowed_extra_flags)` and `lazy.param_hints.keys()` don't raise.
    """
    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Load when demo.\n---\n",
        encoding="utf-8",
    )
    # Bare keys — every collection field is None after yaml.safe_load.
    (skill / "parameters.yaml").write_text(
        "domain: demo\n"
        "script: demo.py\n"
        "saves_h5ad: false\n"
        "requires_preprocessed: false\n"
        "trigger_keywords:\n"
        "legacy_aliases:\n"
        "allowed_extra_flags:\n"
        "param_hints:\n",
        encoding="utf-8",
    )

    lazy = LazySkillMetadata(skill)

    # Each access must succeed AND return the empty default of the right type.
    assert lazy.allowed_extra_flags == set()  # would raise TypeError on None
    assert lazy.trigger_keywords == []
    assert lazy.legacy_aliases == []
    assert lazy.param_hints == {}
    assert isinstance(lazy.param_hints, dict)
    assert lazy.param_hints.keys() == set()  # would raise AttributeError on None


def test_sidecar_used_even_when_frontmatter_is_unparseable(tmp_path: Path) -> None:
    """If SKILL.md has malformed/missing frontmatter (stray BOM, missing
    closing ---), the sidecar must still drive the runtime contract.  Identity
    fields fall back to safe defaults rather than silently zeroing out the
    sidecar."""
    skill = tmp_path / "demo-skill"
    skill.mkdir()
    # No frontmatter fences at all.
    (skill / "SKILL.md").write_text("# Demo\nNo frontmatter here.\n", encoding="utf-8")
    (skill / "parameters.yaml").write_text(
        "domain: demo\n"
        "script: demo.py\n"
        "saves_h5ad: false\n"
        "requires_preprocessed: false\n"
        "trigger_keywords: []\n"
        "legacy_aliases: []\n"
        "allowed_extra_flags: ['--foo']\n"
        "param_hints:\n"
        "  m:\n"
        "    params: ['x']\n"
        "    defaults: {x: 1}\n",
        encoding="utf-8",
    )

    lazy = LazySkillMetadata(skill)

    assert lazy.domain == "demo"
    assert lazy.allowed_extra_flags == {"--foo"}
    assert lazy.param_hints == {"m": {"params": ["x"], "defaults": {"x": 1}}}


def test_no_sidecar_falls_back_to_frontmatter(tmp_path: Path) -> None:
    """Skills without a parameters.yaml continue to read the legacy block."""
    skill = _write_skill(
        tmp_path / "demo-skill",
        frontmatter={
            "name": "demo-skill",
            "description": "Load when demo.",
            "metadata": {
                "omicsclaw": {
                    "domain": "legacy",
                    "allowed_extra_flags": ["--legacy"],
                    "param_hints": {"m": {"params": ["x"], "defaults": {"x": 1}}},
                    "trigger_keywords": ["k"],
                    "saves_h5ad": True,
                }
            },
        },
        sidecar=None,
    )

    lazy = LazySkillMetadata(skill)

    assert lazy.domain == "legacy"
    assert lazy.allowed_extra_flags == {"--legacy"}
    assert lazy.param_hints == {"m": {"params": ["x"], "defaults": {"x": 1}}}
    assert lazy.trigger_keywords == ["k"]
    assert lazy.saves_h5ad is True
