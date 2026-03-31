"""Tests for unified capability resolution and autonomous code validation."""

from omicsclaw.core.capability_resolver import resolve_capability
from omicsclaw.execution import validate_custom_analysis_code


def test_resolve_capability_exact_skill():
    decision = resolve_capability("Run spatial preprocessing on my Visium dataset")
    assert decision.coverage == "exact_skill"
    assert decision.chosen_skill == "spatial-preprocess"
    assert decision.confidence > 0


def test_resolve_capability_partial_skill():
    decision = resolve_capability(
        "Run spatial preprocessing and then compute a custom neighborhood entropy score not in OmicsClaw"
    )
    assert decision.coverage == "partial_skill"
    assert decision.chosen_skill == "spatial-preprocess"
    assert any("custom" in item.lower() for item in decision.missing_capabilities)


def test_resolve_capability_no_skill():
    decision = resolve_capability(
        "Implement a hidden Markov model for chromatin state transition analysis from latest literature"
    )
    assert decision.coverage == "no_skill"
    assert decision.chosen_skill == ""
    assert decision.should_search_web is True


def test_resolve_capability_marks_skill_creation_requests():
    decision = resolve_capability(
        "Create a new OmicsClaw skill for CellCharter-based spatial domain analysis"
    )
    assert decision.should_create_skill is True


def test_validate_custom_analysis_code_blocks_shell_and_network():
    issues = validate_custom_analysis_code(
        "import subprocess\nsubprocess.run(['echo', 'hi'])\n"
    )
    assert any("blocked import" in issue for issue in issues)
    assert any("blocked attribute call" in issue for issue in issues)


def test_validate_custom_analysis_code_allows_basic_analysis():
    issues = validate_custom_analysis_code(
        "import scanpy as sc\nimport pandas as pd\nprint('ok')\n"
    )
    assert issues == []
