"""Behavioural tests for scripts/skill_lint.py.

The lint script enforces the v2 skill template — but only on skills that have
opted in (i.e. have a `parameters.yaml` sidecar).  Legacy skills with only a
frontmatter contract must continue to lint clean by default so the migration
can proceed skill-by-skill.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import skill_lint  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — fabricate skill directories on disk
# ---------------------------------------------------------------------------

VALID_SIDECAR = {
    "domain": "demo",
    "script": "demo.py",
    "saves_h5ad": False,
    "requires_preprocessed": False,
    "trigger_keywords": [],
    "legacy_aliases": [],
    "allowed_extra_flags": ["--method"],
    "param_hints": {},
}

REQUIRED_SECTIONS = (
    "## When to use",
    "## Inputs & Outputs",
    "## Flow",
    "## Gotchas",
    "## Key CLI",
    "## See also",
)

VALID_BODY = (
    "# Demo Skill\n\n"
    "## When to use\nLoad to demo.\n\n"
    "## Inputs & Outputs\nIn → out.\n\n"
    "## Flow\n1. Step.\n\n"
    "## Gotchas\n- _None yet._\n\n"
    "## Key CLI\n```\noc run demo --demo\n```\n\n"
    "## See also\n- references/methodology.md\n"
)


def _write_v2_skill(
    base: Path,
    *,
    description: str = "Load when demoing the lint.",
    body: str = VALID_BODY,
    sidecar: dict | None = None,
    skip_references: tuple[str, ...] = (),
    extra_frontmatter: dict | None = None,
) -> Path:
    skill = base
    skill.mkdir(parents=True, exist_ok=True)
    fm = {
        "name": skill.name,
        "description": description,
        "version": "0.1.0",
        "tags": ["demo"],
    }
    if extra_frontmatter:
        fm.update(extra_frontmatter)
    (skill / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body,
        encoding="utf-8",
    )
    (skill / "parameters.yaml").write_text(
        yaml.safe_dump(sidecar or VALID_SIDECAR, sort_keys=False), encoding="utf-8"
    )
    refs = skill / "references"
    refs.mkdir(exist_ok=True)
    for name in ("methodology.md", "output_contract.md"):
        if name not in skip_references:
            (refs / name).write_text(f"# {name}\n", encoding="utf-8")
    if "parameters.md" not in skip_references:
        from generate_parameters_md import render_parameters_md

        (refs / "parameters.md").write_text(
            render_parameters_md(sidecar or VALID_SIDECAR), encoding="utf-8"
        )
    return skill


def _write_legacy_skill(base: Path) -> Path:
    """Legacy form: SKILL.md with metadata.omicsclaw, no sidecar."""
    skill = base
    skill.mkdir(parents=True, exist_ok=True)
    fm = {
        "name": skill.name,
        "description": "Old-style description.",
        "version": "0.1.0",
        "metadata": {
            "omicsclaw": {
                "domain": "demo",
                "script": "demo.py",
                "allowed_extra_flags": [],
                "param_hints": {},
            }
        },
    }
    (skill / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n# Legacy\n",
        encoding="utf-8",
    )
    return skill


# ---------------------------------------------------------------------------
# Behavioural tests
# ---------------------------------------------------------------------------

def test_valid_v2_skill_lints_clean(tmp_path: Path) -> None:
    skill = _write_v2_skill(tmp_path / "demo")
    errors = skill_lint.lint_skill(skill)
    assert errors == [], f"expected clean lint, got {errors}"


def test_legacy_skill_lints_clean_by_default(tmp_path: Path) -> None:
    """Migration is skill-by-skill; un-migrated skills must not block CI."""
    skill = _write_legacy_skill(tmp_path / "old")
    errors = skill_lint.lint_skill(skill)
    assert errors == [], f"legacy skill should pass default lint, got {errors}"


def test_description_must_start_with_load_when(tmp_path: Path) -> None:
    skill = _write_v2_skill(tmp_path / "demo", description="Differential expression for X.")
    errors = skill_lint.lint_skill(skill)
    assert any("description" in e and "Load when" in e for e in errors)


def test_description_word_count_capped(tmp_path: Path) -> None:
    long_desc = "Load when " + " ".join([f"word{i}" for i in range(60)])
    skill = _write_v2_skill(tmp_path / "demo", description=long_desc)
    errors = skill_lint.lint_skill(skill)
    assert any("description" in e and "50" in e for e in errors)


def test_missing_required_section_fails(tmp_path: Path) -> None:
    body_no_gotchas = VALID_BODY.replace("## Gotchas\n- _None yet._\n\n", "")
    skill = _write_v2_skill(tmp_path / "demo", body=body_no_gotchas)
    errors = skill_lint.lint_skill(skill)
    assert any("## Gotchas" in e for e in errors)


def test_body_too_long_fails(tmp_path: Path) -> None:
    long_body = VALID_BODY + ("filler\n" * 250)
    skill = _write_v2_skill(tmp_path / "demo", body=long_body)
    errors = skill_lint.lint_skill(skill)
    assert any("body" in e.lower() and "200" in e for e in errors)


def test_missing_reference_file_fails(tmp_path: Path) -> None:
    skill = _write_v2_skill(tmp_path / "demo", skip_references=("methodology.md",))
    errors = skill_lint.lint_skill(skill)
    assert any("methodology.md" in e for e in errors)


def test_stale_parameters_md_fails(tmp_path: Path) -> None:
    skill = _write_v2_skill(tmp_path / "demo")
    (skill / "references" / "parameters.md").write_text("STALE\n", encoding="utf-8")
    errors = skill_lint.lint_skill(skill)
    assert any("parameters.md" in e and "stale" in e.lower() for e in errors)


def test_legacy_omicsclaw_block_in_v2_skill_fails(tmp_path: Path) -> None:
    """A v2 skill (parameters.yaml present) must NOT keep the legacy
    metadata.omicsclaw block — otherwise we get two sources of truth."""
    skill = _write_v2_skill(
        tmp_path / "demo",
        extra_frontmatter={"metadata": {"omicsclaw": {"domain": "stale"}}},
    )
    errors = skill_lint.lint_skill(skill)
    assert any("metadata.omicsclaw" in e for e in errors)


def test_sidecar_missing_required_field_fails(tmp_path: Path) -> None:
    bad = dict(VALID_SIDECAR)
    del bad["domain"]
    skill = _write_v2_skill(tmp_path / "demo", sidecar=bad)
    errors = skill_lint.lint_skill(skill)
    assert any("domain" in e for e in errors)


def test_section_inside_html_comment_does_not_satisfy_check(tmp_path: Path) -> None:
    """A required section heading inside an HTML comment should NOT count
    as the section being present (substring-only matching is wrong)."""
    body_with_commented_sections = (
        "# Demo Skill\n\n"
        "<!-- ## When to use ## Inputs & Outputs ## Flow ## Gotchas "
        "## Key CLI ## See also -->\n"
        "Real body content but no actual sections.\n"
    )
    skill = _write_v2_skill(tmp_path / "demo", body=body_with_commented_sections)
    errors = skill_lint.lint_skill(skill)
    # Each missing section should be flagged.
    assert any("## When to use" in e for e in errors)
    assert any("## Gotchas" in e for e in errors)


def test_sidecar_flag_must_start_with_double_dash(tmp_path: Path) -> None:
    bad = dict(VALID_SIDECAR)
    bad["allowed_extra_flags"] = ["method"]  # missing --
    skill = _write_v2_skill(tmp_path / "demo", sidecar=bad)
    errors = skill_lint.lint_skill(skill)
    assert any("allowed_extra_flags" in e for e in errors)
