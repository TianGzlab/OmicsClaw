"""Static method-contract tests for sc-gene-programs."""
from pathlib import Path
MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_gene_programs.py").read_text(encoding="utf-8")
SKILL_TEXT = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")

def test_methods_are_exposed():
    assert 'choices=["cnmf", "nmf"]' in MODULE_TEXT
    assert 'Current Methods' in SKILL_TEXT
    assert '`cnmf`' in SKILL_TEXT
