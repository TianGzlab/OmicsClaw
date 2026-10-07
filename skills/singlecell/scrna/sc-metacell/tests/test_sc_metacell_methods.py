"""Static method-contract tests for sc-metacell."""
from pathlib import Path
MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_metacell.py").read_text(encoding="utf-8")
SKILL_TEXT = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")

def test_methods_are_exposed():
    assert 'choices=["seacells", "kmeans"]' in MODULE_TEXT
    assert 'Methods and parameters' in SKILL_TEXT
    assert 'SEACells' in SKILL_TEXT
    assert 'not sample-aware' in SKILL_TEXT
