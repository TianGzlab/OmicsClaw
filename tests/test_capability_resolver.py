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


def test_resolve_capability_detects_domain_from_multi_suffix_file_path():
    decision = resolve_capability(
        "run variant analysis",
        file_path="/tmp/sample.vcf.gz",
    )
    assert decision.domain == "genomics"


def test_resolve_capability_detects_spatial_microenvironment_subset_skill():
    decision = resolve_capability(
        "Extract a tumor microenvironment neighborhood subset within 50 microns around tumor cells"
    )
    assert decision.coverage == "exact_skill"
    assert decision.chosen_skill == "spatial-microenvironment-subset"



def test_resolve_capability_routes_spatial_raw_fastq_requests_to_spatial_domain():
    decision = resolve_capability(
        "Run st_pipeline on these Visium spatial FASTQs with barcode coordinates",
        file_path="/tmp/sample_R1.fastq.gz",
    )
    assert decision.domain == "spatial"
    assert decision.chosen_skill == "spatial-raw-processing"


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


def test_resolve_capability_breaks_score_ties_alphabetically():
    """The candidate sort must tie-break on the canonical alias so the same
    query produces the same ``chosen_skill`` regardless of which order
    ``registry.iter_primary_skills`` happens to return tied skills in.

    Pre-fix this test failed about half the time depending on filesystem
    traversal at registry load — ``bulkrna-coexpression`` and
    ``bulkrna-ppi-network`` both score 7.25 for this WGCNA query, and
    Python's stable sort kept whichever the registry yielded first.
    """
    decision = resolve_capability(
        "Build a WGCNA co-expression network on my bulk RNA-seq counts, return hub genes"
    )
    top_two = [c.skill for c in decision.skill_candidates[:2]]
    if len(top_two) >= 2 and decision.skill_candidates[0].score == decision.skill_candidates[1].score:
        assert top_two == sorted(top_two), (
            f"tied top candidates must be sorted alphabetically; got {top_two}"
        )
    # And the specific query that originally exposed the flake must produce
    # ``bulkrna-coexpression`` (alphabetically before ``bulkrna-ppi-network``)
    # under any registry iteration order.
    assert decision.chosen_skill == "bulkrna-coexpression"
