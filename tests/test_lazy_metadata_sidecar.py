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
