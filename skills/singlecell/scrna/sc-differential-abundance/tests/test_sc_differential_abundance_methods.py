"""Static method-contract tests for sc-differential-abundance."""
from pathlib import Path
MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_differential_abundance.py").read_text(encoding="utf-8")
SKILL_TEXT = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")

def test_methods_are_exposed():
    assert 'choices=["milo", "sccoda", "simple"]' in MODULE_TEXT
    assert 'Current Methods' in SKILL_TEXT
    assert '`milo`' in SKILL_TEXT
