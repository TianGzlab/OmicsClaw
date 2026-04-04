"""Static method-contract tests for sc-perturb-prep."""

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_perturb_prep.py").read_text(encoding="utf-8")
SKILL_TEXT = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")


def test_mapping_tsv_flags_are_exposed():
    assert "--mapping-file" in MODULE_TEXT
    assert "--control-patterns" in MODULE_TEXT
    assert "`mapping_tsv`" in SKILL_TEXT
