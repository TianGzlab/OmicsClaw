"""Pure-Python tests for the eval-suite assertion helpers.

Uses synthetic ``LLMRoundResult`` instances; no LLM involved, so these
participate in the default ``pytest`` run.
"""

from __future__ import annotations

from tests.eval.assertions import (
    AssertResult,
    assert_calls_tools,
    assert_response_mentions,
    assert_routes_to_skill,
)
from tests.eval.conftest import LLMRoundResult, ToolCallObservation


def _make_result(
    *,
    tool_calls: tuple[ToolCallObservation, ...] = (),
    response_text: str = "",
    query: str = "test",
) -> LLMRoundResult:
    return LLMRoundResult(
        query=query,
        response_text=response_text,
        tool_calls=tool_calls,
        raw=None,
        model="claude-sonnet-4-6",
    )


def _omicsclaw(skill: str) -> ToolCallObservation:
    return ToolCallObservation(name="omicsclaw", arguments={"skill": skill, "mode": "path"})


# --- assert_routes_to_skill ---


def test_routes_to_skill_passes_on_exact_match() -> None:
    result = _make_result(tool_calls=(_omicsclaw("sc-de"),))
    assert assert_routes_to_skill(result, "sc-de").passed


def test_routes_to_skill_passes_on_auto() -> None:
    """Accept auto-routing as correct — we don't force the model to
    pre-resolve the capability resolver."""
    result = _make_result(tool_calls=(_omicsclaw("auto"),))
    assert assert_routes_to_skill(result, "sc-de").passed


def test_routes_to_skill_fails_on_wrong_skill() -> None:
    result = _make_result(tool_calls=(_omicsclaw("spatial-preprocess"),))
    outcome = assert_routes_to_skill(result, "sc-de")
    assert not outcome.passed
    assert any("sc-de" in r and "spatial-preprocess" in r for r in outcome.reasons)


def test_routes_to_skill_fails_when_no_omicsclaw_call() -> None:
    result = _make_result(
        tool_calls=(ToolCallObservation(name="inspect_data", arguments={}),)
    )
    outcome = assert_routes_to_skill(result, "sc-de")
    assert not outcome.passed
    assert any("no omicsclaw" in r for r in outcome.reasons)


def test_routes_to_skill_no_op_on_empty_expected() -> None:
    """When the case doesn't pin a skill, the helper should pass through."""
    result = _make_result()
    assert assert_routes_to_skill(result, "").passed


# --- assert_calls_tools ---


def test_calls_tools_passes_when_all_required_called() -> None:
    result = _make_result(
        tool_calls=(
            ToolCallObservation(name="omicsclaw", arguments={}),
            ToolCallObservation(name="inspect_data", arguments={}),
        )
    )
    outcome = assert_calls_tools(result, must_call=("omicsclaw", "inspect_data"))
    assert outcome.passed


def test_calls_tools_fails_when_required_missing() -> None:
    result = _make_result(
        tool_calls=(ToolCallObservation(name="omicsclaw", arguments={}),)
    )
    outcome = assert_calls_tools(result, must_call=("omicsclaw", "inspect_data"))
    assert not outcome.passed
    assert any("inspect_data" in r for r in outcome.reasons)


def test_calls_tools_fails_when_forbidden_present() -> None:
    result = _make_result(
        tool_calls=(ToolCallObservation(name="replot_skill", arguments={}),)
    )
    outcome = assert_calls_tools(result, must_not_call=("replot_skill",))
    assert not outcome.passed
    assert any("replot_skill" in r and "forbidden" in r for r in outcome.reasons)


def test_calls_tools_passes_on_empty_constraints() -> None:
    """No must_call and no must_not_call → trivially pass."""
    assert assert_calls_tools(_make_result()).passed


# --- assert_response_mentions ---


def test_response_mentions_passes_on_match() -> None:
    result = _make_result(
        response_text="Filter by padj <= 0.05 (Benjamini-Hochberg adjusted)."
    )
    outcome = assert_response_mentions(
        result,
        must_mention=(r"\bpadj\b", r"Benjamini"),
    )
    assert outcome.passed


def test_response_mentions_fails_on_missing_pattern() -> None:
    result = _make_result(response_text="Just filter by p-value < 0.05.")
    outcome = assert_response_mentions(
        result,
        must_mention=(r"\bpadj\b|FDR",),
    )
    assert not outcome.passed
    assert any("not found" in r for r in outcome.reasons)


def test_response_mentions_fails_on_forbidden_pattern() -> None:
    result = _make_result(response_text="Use sc-enrichment guard before sc-de.")
    outcome = assert_response_mentions(
        result,
        must_not_mention=(r"sc-enrichment\s+guard",),
    )
    assert not outcome.passed
    assert any("forbidden pattern" in r for r in outcome.reasons)


def test_response_mentions_handles_multiline_text() -> None:
    """LLM output is multi-line; helper sets DOTALL so cross-line
    patterns work."""
    result = _make_result(
        response_text="Step 1: load data\nStep 2: run sc-de\nStep 3: filter padj"
    )
    outcome = assert_response_mentions(
        result,
        must_mention=(r"sc-de.*padj",),  # spans newline
    )
    assert outcome.passed


def test_response_mentions_passes_on_empty_constraints() -> None:
    assert assert_response_mentions(_make_result()).passed


def test_assert_result_truthiness_matches_passed() -> None:
    assert bool(AssertResult(passed=True))
    assert not bool(AssertResult(passed=False, reasons=("x",)))
