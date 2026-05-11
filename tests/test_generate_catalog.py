"""Regression tests for scripts/generate_catalog.py.

ADR 2026-05-11 (#1) drift-check rollout uncovered a worktree bug:
the hidden-directory filter used `skill_dir.parts` (absolute path
components), so a checkout at `~/.worktrees/<branch>/skills/...`
matched the `.startswith(".")` rule on the `.worktrees` ancestor and
the generator silently emitted a 0-skill catalog.  Fix: filter the
path RELATIVE to SKILLS_DIR.

This test pins the fix in place — running the generator against a
SKILLS_DIR whose ABSOLUTE path contains a `.hidden` ancestor must still
discover skills under it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import generate_catalog  # noqa: E402


_FAKE_SKILL_MD = """\
---
name: fake-skill
description: Load when running the fake regression skill. Skip when never.
version: 0.1.0
---

# fake-skill

## When to use

Synthetic test fixture for catalog generator regression.
"""


def test_generator_discovers_skills_under_dotted_ancestor(tmp_path, monkeypatch):
    """SKILLS_DIR whose absolute path contains a `.hidden` ancestor MUST
    not filter out skills below it.  Reproduces the worktree-incompat bug
    fixed in scripts/generate_catalog.py."""
    # Set up: tmp_path/.worktrees-like-ancestor/skills/<domain>/<skill>/SKILL.md
    hidden_ancestor = tmp_path / ".worktrees" / "branch-x"
    skills_dir = hidden_ancestor / "skills"
    skill_dir = skills_dir / "fake-domain" / "fake-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_FAKE_SKILL_MD, encoding="utf-8")
    # The skill needs a Python file so has_script is True.
    (skill_dir / "fake_skill.py").write_text("# stub\n", encoding="utf-8")

    # Monkeypatch SKILLS_DIR and stub the alias map (which would otherwise
    # try to load the real registry, irrelevant for this filter test).
    monkeypatch.setattr(generate_catalog, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(generate_catalog, "build_cli_alias_map", lambda: {})

    catalog = generate_catalog.generate_catalog()
    assert catalog["skill_count"] == 1, (
        f"hidden-dir filter regression — catalog should have 1 skill under "
        f"{skills_dir} (which has '.worktrees' as an absolute-path ancestor), "
        f"got {catalog['skill_count']}: {[s.get('name') for s in catalog['skills']]}"
    )
    assert catalog["skills"][0]["name"] == "fake-skill"


def test_generator_still_filters_hidden_dirs_relative_to_skills_dir(tmp_path, monkeypatch):
    """The filter must still exclude `.hidden` / `__dunder__` directories
    when they appear INSIDE the skills tree (e.g. `__pycache__`)."""
    skills_dir = tmp_path / "skills"
    # Real skill
    real_dir = skills_dir / "real-domain" / "real-skill"
    real_dir.mkdir(parents=True)
    (real_dir / "SKILL.md").write_text(_FAKE_SKILL_MD, encoding="utf-8")
    (real_dir / "real_skill.py").write_text("# stub\n", encoding="utf-8")
    # Hidden directory inside skills tree — must be excluded
    hidden_dir = skills_dir / "__pycache__" / "cached-skill"
    hidden_dir.mkdir(parents=True)
    (hidden_dir / "SKILL.md").write_text(_FAKE_SKILL_MD, encoding="utf-8")
    (hidden_dir / "cached_skill.py").write_text("# stub\n", encoding="utf-8")

    monkeypatch.setattr(generate_catalog, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(generate_catalog, "build_cli_alias_map", lambda: {})

    catalog = generate_catalog.generate_catalog()
    assert catalog["skill_count"] == 1, (
        "hidden dirs INSIDE the skills tree must still be filtered"
    )
    assert catalog["skills"][0]["name"] == "fake-skill"
