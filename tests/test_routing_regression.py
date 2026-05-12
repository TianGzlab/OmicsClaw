"""Routing regression suite for the Stage 2–4 architecture.

These are behavior tests for the end-to-end router as used by the bot:

* ``resolve_capability`` scores all 88 skills
* close top-1/top-2 gap (< ``_AUTO_DISAMBIGUATE_GAP``) triggers disambiguation
* file extension should disambiguate between cross-domain same-name skills

Cases are declared as data (not a test function per query) so adding coverage
stays a one-line change. Every row asserts either a ``chosen_skill`` or an
``ambiguous`` signal — never both — so drift shows up as a specific failure.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from omicsclaw.core.capability_resolver import resolve_capability


@dataclass(frozen=True)
class _Case:
    label: str
    query: str
    file_path: str = ""
    # Exactly one of the three expectations should be non-empty.
    expect_skill: str = ""          # canonical chosen_skill alias
    expect_ambiguous_between: tuple[str, ...] = ()  # top-K should include these
    expect_coverage: str = ""       # e.g. "no_skill"


_CLEAR_INTENT_CASES: list[_Case] = [
    _Case(
        "clear visium preprocess",
        "run spatial preprocessing on my Visium dataset",
        expect_skill="spatial-preprocess",
    ),
    _Case(
        "clear WGCNA on bulk",
        "Build a WGCNA co-expression network on my bulk RNA-seq counts, return hub genes",
        expect_skill="bulkrna-coexpression",
    ),
    _Case(
        "clear Kaplan-Meier survival",
        "Run Kaplan-Meier survival for TP53 expression with clinical overall survival",
        expect_skill="bulkrna-survival",
    ),
]

# Known resolver weaknesses surfaced by Stage 5 — kept as tracked xfails so
# they turn green automatically when the resolver is fixed.
_CLEAR_INTENT_XFAILS: list[_Case] = [
    _Case(
        "BAM variant calling rejected by analysis gate",
        "call SNVs and indels from this BAM using GATK",
        expect_skill="genomics-variant-calling",
    ),
    _Case(
        "peptide identification rejected by analysis gate",
        "Identify peptides with MaxQuant from my raw MS files",
        expect_skill="proteomics-identification",
    ),
    # XCMS-specific vocabulary loses to ``spatial-preprocess`` because the
    # word "preprocess" dominates the score before metabolomics-domain
    # signals can break the tie. Tracked here so a future domain-aware
    # tie-break turns the case green automatically.
    _Case(
        "clear XCMS preprocessing",
        "Preprocess this LC-MS dataset with XCMS: peak detection and RT alignment",
        expect_skill="metabolomics-xcms-preprocessing",
    ),
]


_FILE_EXTENSION_CASES: list[_Case] = [
    _Case(
        "spatial fastq path stays spatial",
        "run st_pipeline with barcode coordinates",
        file_path="/tmp/sample_R1.fastq.gz",
        expect_skill="spatial-raw-processing",
    ),
]

_FILE_EXTENSION_XFAILS: list[_Case] = [
    # The resolver's domain detection from ``.vcf.gz`` is correct, but
    # ``iter_primary_skills(domain=...)`` does not appear to hard-filter
    # the candidate pool, so ``spatial-annotate`` (legacy alias ``annotate``)
    # still outscores the genomics option for the word "annotate".
    _Case(
        "vcf path should lock routing to genomics",
        "annotate variants in this file",
        file_path="/tmp/sample.vcf.gz",
        expect_skill="genomics-variant-annotation",
    ),
]


_NO_SKILL_CASES: list[_Case] = [
    _Case(
        "HMM from literature (no skill)",
        "Implement a hidden Markov model for chromatin state transitions from latest literature",
        expect_coverage="no_skill",
    ),
    _Case(
        "off-topic chit-chat",
        "what's the weather in Beijing",
        expect_coverage="no_skill",
    ),
]


_AMBIGUOUS_CASES: list[_Case] = [
    # No currently-exercisable cases — see the docstring above
    # ``test_disambiguation_gate_architecturally_intact`` for the reasoning.
    # When resolver scoring is balanced across domains (see xfails below)
    # add real cases here.
]

_AMBIGUOUS_XFAILS: list[_Case] = [
    # Canonical cross-domain ambiguity. Should surface candidates from at
    # least two of {bulkrna, sc, spatial, proteomics, metabolomics}. Today
    # the resolver pins the query to one domain and silently picks top-1.
    _Case(
        "cross-domain enrichment must expose candidates from ≥2 domains",
        "run pathway enrichment on my differentially expressed gene list",
        expect_ambiguous_between=(
            "bulkrna-enrichment",
            "sc-enrichment",
            "spatial-enrichment",
            "proteomics-enrichment",
            "metabolomics-pathway-enrichment",
        ),
    ),
]


# ---------------------------------------------------------------------------
# Parameterized dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CLEAR_INTENT_CASES, ids=lambda c: c.label)
def test_clear_intent_routes_to_expected_skill(case: _Case):
    decision = resolve_capability(case.query, file_path=case.file_path)
    assert decision.chosen_skill == case.expect_skill, (
        f"{case.label}: expected {case.expect_skill!r}, got {decision.chosen_skill!r}; "
        f"top candidates: {[(c.skill, round(c.score, 2)) for c in decision.skill_candidates[:3]]}"
    )
    assert decision.coverage in {"exact_skill", "partial_skill"}


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Known resolver weakness: certain analysis verbs (e.g. 'call', "
        "'Identify') fail the `_looks_like_analysis_request` gate when no "
        "file_path is given, even though the query is obviously an analysis "
        "request. Tracked here so a future fix flips these to passing."
    ),
)
@pytest.mark.parametrize("case", _CLEAR_INTENT_XFAILS, ids=lambda c: c.label)
def test_clear_intent_known_resolver_gaps(case: _Case):
    decision = resolve_capability(case.query, file_path=case.file_path)
    assert decision.chosen_skill == case.expect_skill


@pytest.mark.parametrize("case", _FILE_EXTENSION_CASES, ids=lambda c: c.label)
def test_file_extension_drives_routing(case: _Case):
    decision = resolve_capability(case.query, file_path=case.file_path)
    assert decision.chosen_skill == case.expect_skill, (
        f"{case.label}: expected {case.expect_skill!r}, got {decision.chosen_skill!r}"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Known resolver weakness: a file path's detected domain doesn't "
        "hard-filter the candidate pool, so legacy aliases from other "
        "domains (e.g. spatial-annotate) can still win on a .vcf query."
    ),
)
@pytest.mark.parametrize("case", _FILE_EXTENSION_XFAILS, ids=lambda c: c.label)
def test_file_extension_routing_known_gaps(case: _Case):
    decision = resolve_capability(case.query, file_path=case.file_path)
    assert decision.chosen_skill == case.expect_skill


@pytest.mark.parametrize("case", _NO_SKILL_CASES, ids=lambda c: c.label)
def test_no_skill_paths_return_fallback(case: _Case):
    decision = resolve_capability(case.query, file_path=case.file_path)
    assert decision.coverage == "no_skill", (
        f"{case.label}: expected no_skill, got {decision.coverage}; "
        f"chosen_skill={decision.chosen_skill!r}"
    )
    assert decision.chosen_skill == ""


@pytest.mark.skipif(not _AMBIGUOUS_CASES, reason="no exercisable cases yet")
@pytest.mark.parametrize("case", _AMBIGUOUS_CASES or [_Case("placeholder", "")], ids=lambda c: c.label)
def test_ambiguity_surfaces_candidates(case: _Case):
    """Ambiguous queries MUST expose multiple candidates so the bot's
    disambiguation gate (Stage 3b) can trigger — otherwise the bot would
    silently run the top-1 guess."""
    decision = resolve_capability(case.query, file_path=case.file_path)
    assert len(decision.skill_candidates) >= 2, (
        f"{case.label}: expected at least 2 candidates, got "
        f"{len(decision.skill_candidates)}"
    )
    seen = {c.skill for c in decision.skill_candidates}
    overlap = seen & set(case.expect_ambiguous_between)
    assert len(overlap) >= 2, (
        f"{case.label}: expected top candidates to include at least 2 of "
        f"{case.expect_ambiguous_between}; got {seen}"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Known resolver weakness: domain-detection in ``_detect_domain`` "
        "currently over-commits (e.g. 'pathway' locks the query to spatial). "
        "For truly cross-domain queries the candidate list should span ≥2 "
        "domains so the Stage 3b disambiguation gate can fire."
    ),
)
@pytest.mark.parametrize("case", _AMBIGUOUS_XFAILS, ids=lambda c: c.label)
def test_cross_domain_ambiguity_known_gaps(case: _Case):
    decision = resolve_capability(case.query, file_path=case.file_path)
    seen = {c.skill for c in decision.skill_candidates}
    overlap = seen & set(case.expect_ambiguous_between)
    assert len(overlap) >= 2


def test_disambiguation_gate_architecturally_intact():
    """Sanity-check: the Stage 3b disambiguation constant and helper exist
    and can handle a synthetic close-tie decision.

    Note on the resolver's current scoring distribution: trigger-keyword
    hits add ~5+ points to top-1, so real queries either produce a clear
    winner (gap >> 2.0) or a noisy pool below the 3.0 ``chosen_skill``
    threshold. The gate is correct but rarely fires on organic traffic —
    once we have real bot logs it'll be worth re-tuning
    ``_AUTO_DISAMBIGUATE_GAP`` against observed top1/top2 distributions.
    """
    from bot.core import _AUTO_DISAMBIGUATE_GAP, _format_auto_disambiguation
    from omicsclaw.core.capability_resolver import (
        CapabilityCandidate,
        CapabilityDecision,
    )

    assert 0 < _AUTO_DISAMBIGUATE_GAP < 10.0
    # Synthetic close tie: helper must format a non-empty block.
    dec = CapabilityDecision(
        query="q",
        chosen_skill="sc-de",
        skill_candidates=[
            CapabilityCandidate(skill="sc-de", domain="singlecell", score=5.5, reasons=["a"]),
            CapabilityCandidate(skill="sc-markers", domain="singlecell", score=5.0, reasons=["b"]),
        ],
    )
    block = _format_auto_disambiguation(dec, "q")
    assert "`sc-de`" in block and "`sc-markers`" in block
