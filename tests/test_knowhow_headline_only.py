"""Phase 2 (Tasks 2.1 + 2.2) of the system-prompt-compression refactor.

These tests pin three behavioral changes to ``KnowHowInjector``:

1. ``get_constraints`` emits *only* headline rows (``→ {label}: {critical_rule}``)
   by default — no full KH body. This compresses the largest single source
   in the system prompt (~9.8KB → ~800c on realistic queries).

2. Match cardinality is capped at K=4 to bound prompt growth on broad queries.

3. ``KH-sc-enrichment-guardrails.md`` no longer over-fires on ``skill="sc-de"``
   queries — the bug was that its frontmatter listed sc-de under
   ``related_skills`` (a *related* signal), which previously scored equal to
   a *primary* skill match. The fix tiers primary vs related so loose
   relations require a corroborating keyword/domain signal.

Reference:
- KH-sc-de-guardrails.md is the primary KH for sc-de.
- KH-sc-enrichment-guardrails.md is the primary KH for sc-enrichment;
  it also relates to sc-de but should only fire when the query mentions
  enrichment / pathway scoring intent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.knowledge.knowhow import KnowHowInjector

ROOT = Path(__file__).resolve().parent.parent
KNOWHOW_DIR = ROOT / "knowledge_base" / "knowhows"


def _injector() -> KnowHowInjector:
    return KnowHowInjector(knowhows_dir=KNOWHOW_DIR)


# --- Headline-only mode -------------------------------------------------------


def test_get_constraints_emits_only_headlines_when_opted_in() -> None:
    """``headline_only=True`` (the production-path opt-in) suppresses the
    full KH bodies and emits only ``→ {label}: {critical_rule}`` headlines.

    The default remains ``headline_only=False`` for backward-compat with
    callers / tests that assert on body content; the production
    ``load_knowhow_constraints`` helper opts into ``True``.
    """
    text = _injector().get_constraints(
        skill="sc-de",
        query="run sc-de differential expression",
        domain="singlecell",
        headline_only=True,
    )
    assert text, "expected non-empty constraints for sc-de query"
    assert "**Active guards for this task:**" in text
    assert "  → " in text, "headline rows missing"
    assert "### 📋" not in text, (
        "body section heading present — headline-only mode should suppress bodies"
    )
    # Compression sanity: the entire payload should be well under 2KB.
    assert len(text) < 2000, f"expected headline-only payload <2KB, got {len(text)} chars"


def test_get_constraints_default_is_full_body_for_test_compat() -> None:
    """The bare default keeps the legacy full-body output so existing tests
    asserting on body content continue to pass without modification.

    Phase 2 production callers explicitly opt into ``headline_only=True``;
    this test pins the contract that the default is *not* the compressed
    mode so the same default never breaks unmigrated callers silently.
    """
    text = _injector().get_constraints(
        skill="sc-de",
        query="run sc-de differential expression",
        domain="singlecell",
    )
    assert text
    assert "### 📋" in text, "body section heading missing in legacy default"


# --- K=4 cap ------------------------------------------------------------------


def test_get_constraints_caps_match_count_at_4() -> None:
    """Even when many KHs match, only the top 4 should be emitted.

    Using a query that previously matched 5+ KHs (sc-de under singlecell).
    """
    text = _injector().get_constraints(
        skill="sc-de",
        query="do single-cell differential expression analysis",
        domain="singlecell",
    )
    # Count headline arrow rows; each is one matched KH.
    arrow_lines = [line for line in text.splitlines() if line.strip().startswith("→ ")]
    assert len(arrow_lines) <= 4, (
        f"expected at most 4 headline rows, got {len(arrow_lines)}: "
        f"{[line.strip() for line in arrow_lines]}"
    )


# --- sc-enrichment over-match fix ---------------------------------------------


def test_sc_enrichment_kh_does_not_match_plain_sc_de_query() -> None:
    """The reported bug: sc-enrichment-guardrails fires on ``skill='sc-de'``
    even when the user query has no enrichment intent. After the fix, it
    should not appear in the matched IDs."""
    matches = _injector().get_matching_kh_ids(
        skill="sc-de",
        query="run sc-de on my single-cell data",
        domain="singlecell",
    )
    assert "KH-sc-enrichment-guardrails.md" not in matches, (
        "sc-enrichment KH should not over-match a plain sc-de query; "
        f"got matches: {matches}"
    )


def test_sc_enrichment_kh_still_matches_when_skill_is_sc_enrichment() -> None:
    """Regression: the strict primary-skill match path must still fire."""
    matches = _injector().get_matching_kh_ids(
        skill="sc-enrichment",
        query="run sc-enrichment on marker results",
        domain="singlecell",
    )
    assert "KH-sc-enrichment-guardrails.md" in matches, (
        f"primary-skill match for sc-enrichment lost; got: {matches}"
    )


def test_sc_enrichment_kh_matches_when_query_mentions_enrichment() -> None:
    """When the user query explicitly mentions enrichment (cross-skill
    intent), the related KH should still surface even with skill='sc-de'."""
    matches = _injector().get_matching_kh_ids(
        skill="sc-de",
        query="do enrichment after sc-de differential expression",
        domain="singlecell",
    )
    assert "KH-sc-enrichment-guardrails.md" in matches, (
        f"enrichment-keyword fallback path lost; got: {matches}"
    )


def test_sc_de_kh_remains_top_match_for_sc_de_query() -> None:
    """Sanity: the canonical sc-de KH remains the top match for a sc-de query."""
    matches = _injector().get_matching_kh_ids(
        skill="sc-de",
        query="run sc-de on my single-cell data",
        domain="singlecell",
    )
    assert "KH-sc-de-guardrails.md" in matches[:2], (
        f"sc-de primary KH should be among top-2; got: {matches}"
    )
