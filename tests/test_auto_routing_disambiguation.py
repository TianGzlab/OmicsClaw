"""Tests for Stage 3 auto-routing helpers in ``bot.core``.

Covers the two output-shaping functions that were added to make the ``auto``
path interact with the LLM safely:

* ``_format_auto_disambiguation`` — returns a candidate list when the top two
  scores are within ``_AUTO_DISAMBIGUATE_GAP``.
* ``_format_auto_route_banner`` — returns a short ``📍 Auto-routed …`` banner
  that gets prepended to successful tool output.

We do not exercise the full ``execute_omicsclaw`` subprocess pipeline here —
that would require a live subprocess and demo data. Instead we build the
``CapabilityDecision`` shape directly and assert on the formatted text.
"""

from __future__ import annotations

from omicsclaw.core.capability_resolver import (
    CapabilityCandidate,
    CapabilityDecision,
)


def _decision(
    chosen: str,
    confidence: float,
    candidates: list[tuple[str, float, list[str]]],
    coverage: str = "exact_skill",
) -> CapabilityDecision:
    """Build a minimal CapabilityDecision matching the resolver's shape."""
    return CapabilityDecision(
        query="dummy",
        domain="",
        coverage=coverage,
        confidence=confidence,
        chosen_skill=chosen,
        skill_candidates=[
            CapabilityCandidate(
                skill=name, domain="", score=score, reasons=list(reasons)
            )
            for name, score, reasons in candidates
        ],
    )


# ---------------------------------------------------------------------------
# _format_auto_route_banner
# ---------------------------------------------------------------------------


def test_auto_route_banner_shows_chosen_and_confidence():
    from bot.core import _format_auto_route_banner

    dec = _decision(
        chosen="sc-de",
        confidence=0.73,
        candidates=[
            ("sc-de", 10.5, ["trigger keyword match: differential expression"]),
            ("sc-markers", 7.1, ["trigger keyword match: marker genes"]),
        ],
    )
    banner = _format_auto_route_banner(dec)

    assert banner.startswith("📍 Auto-routed to `sc-de`")
    assert "confidence 0.73" in banner
    # A close alternative should be disclosed so the LLM can pivot if wrong.
    assert "sc-markers" in banner
    # The banner terminates with a markdown divider so the real tool output
    # stays visually separated.
    assert banner.rstrip().endswith("---")


def test_auto_route_banner_without_alternatives():
    from bot.core import _format_auto_route_banner

    dec = _decision(
        chosen="spatial-preprocess",
        confidence=0.95,
        candidates=[("spatial-preprocess", 13.0, ["alias hit"])],
    )
    banner = _format_auto_route_banner(dec)

    assert "spatial-preprocess" in banner
    assert "confidence 0.95" in banner
    # No alternatives in the candidate list → no "Close alternatives" phrase.
    assert "Close alternatives" not in banner


# ---------------------------------------------------------------------------
# _format_auto_disambiguation
# ---------------------------------------------------------------------------


def test_disambiguation_lists_top_three_candidates():
    from bot.core import _format_auto_disambiguation

    dec = _decision(
        chosen="bulkrna-de",
        confidence=0.62,
        candidates=[
            ("bulkrna-de", 8.0, ["description token overlap: differential"]),
            ("spatial-de", 7.3, ["trigger keyword match: differential expression"]),
            ("sc-de", 7.0, ["trigger keyword match: de"]),
        ],
    )
    block = _format_auto_disambiguation(dec, query_text="find differentially expressed genes")

    # Human-readable header prevents the LLM from silently re-running the wrong skill.
    assert "Auto-routing found multiple close candidates" in block
    # All three candidate aliases must be surfaced for LLM selection.
    for alias in ("bulkrna-de", "spatial-de", "sc-de"):
        assert f"`{alias}`" in block
    # Quantitative scores give the LLM a concrete tie-breaker signal.
    assert "8.00" in block and "7.30" in block
    # Explicit instruction to re-invoke with a specific skill.
    assert "re-invoke" in block.lower()
    assert "skill=" in block


def test_disambiguation_handles_empty_candidate_list():
    from bot.core import _format_auto_disambiguation

    dec = _decision(chosen="", confidence=0.0, candidates=[])
    block = _format_auto_disambiguation(dec, query_text="nothing matches")

    # No candidates → the helper should produce no output rather than a
    # malformed "Top candidates" block. This protects callers that iterate
    # output lines.
    assert block == ""


def test_disambiguation_truncates_long_description():
    from bot.core import _format_auto_disambiguation
    import bot.core as bc

    # Monkey-patch the registry lookup so this test doesn't depend on the
    # live SKILL.md content (which changes as the repo grows).
    class _FakeRegistry:
        skills = {
            "fake-skill": {
                "description": "x" * 300,  # deliberately long
            },
            "other-skill": {"description": "short"},
        }

    original = bc._skill_registry
    bc._skill_registry = lambda: _FakeRegistry()  # type: ignore[assignment]
    try:
        dec = _decision(
            chosen="fake-skill",
            confidence=0.4,
            candidates=[
                ("fake-skill", 5.0, []),
                ("other-skill", 4.2, []),
            ],
        )
        block = _format_auto_disambiguation(dec, query_text="q")
    finally:
        bc._skill_registry = original  # type: ignore[assignment]

    # Truncation marker appears; the raw 300-char payload must not be inlined.
    assert "…" in block
    assert "x" * 300 not in block


# ---------------------------------------------------------------------------
# _AUTO_DISAMBIGUATE_GAP
# ---------------------------------------------------------------------------


def test_disambiguate_gap_is_calibrated():
    """Sanity-check the threshold: too low and we never disambiguate, too
    high and we refuse to execute on most queries. The scorer typically
    gives 0.85 per trigger-keyword hit and ~10 for alias hits, so 2.0 is a
    reasonable dead-zone between "one extra keyword" and "clearly better"."""
    from bot.core import _AUTO_DISAMBIGUATE_GAP

    assert 1.0 <= _AUTO_DISAMBIGUATE_GAP <= 4.0
