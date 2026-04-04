"""Static method-contract tests for sc-perturb."""

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_perturb.py").read_text(encoding="utf-8")
SKILL_TEXT = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")


def test_mixscape_is_exposed():
    assert 'choices=["mixscape"]' in MODULE_TEXT
    assert '`mixscape`' in SKILL_TEXT
    assert "--pert-key" in SKILL_TEXT
