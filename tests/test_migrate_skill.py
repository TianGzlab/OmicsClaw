"""Behavioural tests for scripts/migrate_skill.py.

The migration script extracts the legacy `metadata.omicsclaw` block from a
skill's SKILL.md frontmatter into a `parameters.yaml` sidecar, then writes
SKILL.md.new with a thin v2 frontmatter and body skeleton.  The single
non-negotiable invariant: LazySkillMetadata's runtime contract is
bit-identical before and after migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import migrate_skill  # noqa: E402

from omicsclaw.core.lazy_metadata import LazySkillMetadata  # noqa: E402


LEGACY_FRONTMATTER = {
    "name": "demo-skill",
    "description": "Old-style what-it-does description.",
    "version": "0.3.0",
    "tags": ["demo", "diff-expr"],
    "metadata": {
        "omicsclaw": {
            "domain": "demo",
            "script": "demo_skill.py",
            "trigger_keywords": ["demo", "demo skill"],
            "allowed_extra_flags": ["--method", "--padj"],
            "legacy_aliases": ["demo-old"],
            "saves_h5ad": False,
            "requires_preprocessed": False,
            "param_hints": {
                "wilcoxon": {
                    "priority": "groupby -> corr",
                    "params": ["groupby"],
                    "defaults": {"groupby": "leiden"},
                    "requires": ["obs.groupby"],
                    "tips": ["Pick groupby first."],
                }
            },
        }
    },
}

LEGACY_BODY = (
    "# Demo Skill\n\n"
    "## Why This Exists\n\n"
    "Demo rationale paragraph.\n\n"
    "## Algorithm\n\n"
    "1. Load.\n"
    "2. Run.\n\n"
    "**Note:** PyDESeq2 falls back to t-test when no replicates.\n\n"
    "## Output Structure\n\n"
    "```\n"
    "output/\n"
    "├── report.md\n"
    "└── tables/\n"
    "```\n\n"
    "## Citations\n\n"
    "- Cite 1\n"
)


def _write_legacy(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(LEGACY_FRONTMATTER, sort_keys=False) + "---\n\n" + LEGACY_BODY,
        encoding="utf-8",
    )
    return base


def _runtime_snapshot(skill: Path) -> dict:
    """Snapshot every public field of LazySkillMetadata that the registry
    consumes.  Used to assert the migration is contract-preserving."""
    lazy = LazySkillMetadata(skill)
    return {
        "name": lazy.name,
        "description": lazy.description,
        "domain": lazy.domain,
        "script": lazy.script,
        "trigger_keywords": list(lazy.trigger_keywords),
        "legacy_aliases": list(lazy.legacy_aliases),
        "allowed_extra_flags": set(lazy.allowed_extra_flags),
        "saves_h5ad": lazy.saves_h5ad,
        "requires_preprocessed": lazy.requires_preprocessed,
        "param_hints": dict(lazy.param_hints),
    }


# ---------------------------------------------------------------------------
# Slice 1: sidecar extraction + roundtrip
# ---------------------------------------------------------------------------

def test_migrate_writes_parameters_yaml(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    migrate_skill.migrate(skill)
    sidecar = skill / "parameters.yaml"
    assert sidecar.exists()


def test_runtime_contract_unchanged_after_migration(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    before = _runtime_snapshot(skill)
    migrate_skill.migrate(skill)
    # Promote SKILL.md.new -> SKILL.md to simulate the maintainer accepting
    # the migration; only at this point should the runtime read the new form.
    (skill / "SKILL.md").unlink()
    (skill / "SKILL.md.new").rename(skill / "SKILL.md")
    after = _runtime_snapshot(skill)
    assert before == after, f"runtime contract changed:\nbefore={before}\nafter={after}"


def test_sidecar_does_not_carry_identity_fields(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    migrate_skill.migrate(skill)
    sidecar = yaml.safe_load((skill / "parameters.yaml").read_text())
    for forbidden in ("name", "description", "version", "tags"):
        assert forbidden not in sidecar


# ---------------------------------------------------------------------------
# Slice 2: SKILL.md.new structure
# ---------------------------------------------------------------------------

def test_skill_md_new_has_thin_frontmatter(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    migrate_skill.migrate(skill)
    text = (skill / "SKILL.md.new").read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---", 2)[1])
    assert "metadata" not in fm, "v2 frontmatter must not carry metadata.omicsclaw"
    assert fm["name"] == "demo-skill"
    assert fm["description"] == LEGACY_FRONTMATTER["description"]
    assert fm["version"] == "0.3.0"


def test_skill_md_new_includes_required_sections(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    migrate_skill.migrate(skill)
    body = (skill / "SKILL.md.new").read_text(encoding="utf-8").split("---", 2)[2]
    for section in ("## When to use", "## Inputs & Outputs", "## Flow",
                    "## Gotchas", "## Key CLI", "## See also"):
        assert section in body, f"missing section: {section}"


def test_skill_md_original_not_overwritten(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    original = (skill / "SKILL.md").read_text()
    migrate_skill.migrate(skill)
    assert (skill / "SKILL.md").read_text() == original


# ---------------------------------------------------------------------------
# Slice 3: references slicing
# ---------------------------------------------------------------------------

def test_methodology_extracted_to_references(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    migrate_skill.migrate(skill)
    methodology = (skill / "references" / "methodology.md").read_text()
    assert "1. Load." in methodology
    assert "2. Run." in methodology


def test_output_contract_extracted(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    migrate_skill.migrate(skill)
    output_md = (skill / "references" / "output_contract.md").read_text()
    assert "report.md" in output_md


def test_parameters_md_generated_from_sidecar(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    migrate_skill.migrate(skill)
    params_md = (skill / "references" / "parameters.md").read_text()
    assert "AUTO-GENERATED" in params_md
    assert "wilcoxon" in params_md  # method from sidecar
    assert "--method" in params_md  # flag from sidecar


# ---------------------------------------------------------------------------
# Slice 4: migration aids
# ---------------------------------------------------------------------------

def test_gotcha_candidates_mined(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    migrate_skill.migrate(skill)
    gotchas = (skill / "_migration" / "gotcha-candidates.md").read_text()
    assert "falls back" in gotchas.lower() or "no replicates" in gotchas.lower()


def test_description_suggestions_emitted(tmp_path: Path) -> None:
    skill = _write_legacy(tmp_path / "demo-skill")
    migrate_skill.migrate(skill)
    suggestions = (skill / "_migration" / "description-suggestions.md").read_text()
    assert "Load when" in suggestions
    assert LEGACY_FRONTMATTER["description"] in suggestions
