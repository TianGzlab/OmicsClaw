"""Static method-contract tests for sc-tenifold-knockout."""

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_tenifold_knockout.py").read_text(encoding="utf-8")
SKILL_TEXT = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")


def test_sctenifoldknk_flags_are_exposed():
    assert "--ko-gene" in MODULE_TEXT
    assert "--n-net" in MODULE_TEXT
    assert "scTenifoldKnk" in SKILL_TEXT
