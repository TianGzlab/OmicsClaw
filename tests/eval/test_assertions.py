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


def test_routes_to_skill_accepts_read_knowhow_kh_signal() -> None:
    """``read_knowhow(name='KH-<skill>-*')`` is a strong routing signal in
    multi-round agent traces — the model loading the skill's KH means it
    has already decided to route there, even when the subsequent
    ``omicsclaw`` call lands in the next round the eval doesn't capture."""
    result = _make_result(
        tool_calls=(
            ToolCallObservation(name="inspect_data", arguments={"file_path": "/tmp/x.h5ad"}),
            ToolCallObservation(name="read_knowhow", arguments={"name": "KH-sc-de-guardrails.md"}),
        )
    )
    assert assert_routes_to_skill(result, "sc-de").passed


def test_routes_to_skill_unrelated_kh_does_not_count() -> None:
    """A KH from a different skill must not cross-validate routing."""
    result = _make_result(
        tool_calls=(
            ToolCallObservation(name="read_knowhow", arguments={"name": "KH-spatial-preprocess.md"}),
        )
    )
    outcome = assert_routes_to_skill(result, "sc-de")
    assert not outcome.passed


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


def test_response_mentions_inconclusive_on_inspection_only_round() -> None:
    """First-round agent traces may have empty response_text because the
    model used the round entirely for inspection tools. Skip the mention
    check in that case — the substantive response lives in the follow-up
    round the single-round eval doesn't capture. SOUL.md explicitly
    encourages inspect-before-action; punishing it would over-fit eval
    to behavior production never demands."""
    result = _make_result(
        response_text="",
        tool_calls=(
            ToolCallObservation(name="inspect_data", arguments={"file_path": "/tmp/x.h5ad"}),
            ToolCallObservation(name="read_knowhow", arguments={"name": "KH-sc-de.md"}),
        ),
    )
    outcome = assert_response_mentions(result, must_mention=(r"\bpadj\b",))
    assert outcome.passed


def test_response_mentions_still_fails_when_response_present_but_missing() -> None:
    """Sanity: inspection-tolerance only kicks in for *empty* response_text.
    Once the model has emitted text content, missing patterns are real."""
    result = _make_result(
        response_text="Here is some explanation but no statistical term.",
        tool_calls=(ToolCallObservation(name="inspect_data", arguments={}),),
    )
    outcome = assert_response_mentions(result, must_mention=(r"\bpadj\b",))
    assert not outcome.passed


def test_response_mentions_still_fails_on_empty_with_non_inspection_tool() -> None:
    """If the empty response is paired with a non-inspection tool
    (e.g. ``omicsclaw`` itself), the model has already taken substantive
    action — empty text plus missing pattern is a real signal failure."""
    result = _make_result(
        response_text="",
        tool_calls=(ToolCallObservation(name="omicsclaw", arguments={"skill": "sc-de"}),),
    )
    outcome = assert_response_mentions(result, must_mention=(r"\bpadj\b",))
    assert not outcome.passed


def test_assert_result_truthiness_matches_passed() -> None:
    assert bool(AssertResult(passed=True))
    assert not bool(AssertResult(passed=False, reasons=("x",)))
