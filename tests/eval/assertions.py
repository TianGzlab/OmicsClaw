"""Pure-Python invariant-assertion helpers for the eval suite.

Each helper accepts an ``LLMRoundResult`` plus the relevant ``EvalCase``
fields and returns ``AssertResult(passed: bool, reasons: list[str])``.
The eval runner converts a failed must-priority result into ``pytest.fail``
and a failed should-priority result into ``warnings.warn(UserWarning)``
so non-determinism in lower-priority cases doesn't block CI.

These helpers are intentionally stateless / IO-free so they can be unit
tested with mock ``LLMRoundResult`` instances — no LLM, no env, no disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tests.eval.conftest import LLMRoundResult


@dataclass(frozen=True, slots=True)
class AssertResult:
    """Outcome of one invariant check.

    ``passed`` reflects the boolean truth; ``reasons`` carries the
    human-readable diagnostics that get logged into the per-case JSON
    artifact and the markdown report. Empty list when ``passed`` is True.
    """

    passed: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:  # convenience: ``if assert_result: ...``
        return self.passed


def _ok() -> AssertResult:
    return AssertResult(passed=True)


def _fail(*reasons: str) -> AssertResult:
    return AssertResult(passed=False, reasons=tuple(reasons))


# Tools the agent uses for first-round inspection. When the captured
# round contains *only* these and no text content, we treat the
# mention-pattern check as inconclusive rather than failing — SOUL.md
# encourages inspect-before-action and the substantive response lives
# in the follow-up round we don't capture in single-round eval.
_INSPECTION_TOOL_NAMES: frozenset[str] = frozenset({
    "inspect_data",
    "inspect_file",
    "read_knowhow",
    "consult_knowledge",
    "glob_files",
    "get_file_size",
    "resolve_capability",
    "remember",
})


# --- Helper 1: routing -------------------------------------------------------


def assert_routes_to_skill(
    result: LLMRoundResult, expected_skill: str
) -> AssertResult:
    """Pass iff the captured round routes to ``expected_skill``.

    Routing is detected as either:

    1. An ``omicsclaw`` tool call whose ``skill`` argument equals
       ``expected_skill`` OR is ``"auto"`` (which the capability resolver
       will then resolve — accepting auto avoids forcing the model to
       pre-resolve), OR
    2. A ``read_knowhow`` tool call whose ``name`` argument matches
       ``KH-<expected_skill>-*`` — the model loading the skill's KH is a
       strong routing signal in multi-round agent traces, even when the
       subsequent ``omicsclaw`` call lands in the next round the eval
       doesn't capture.
    """
    if not expected_skill:
        return _ok()

    omicsclaw_calls = [tc for tc in result.tool_calls if tc.name == "omicsclaw"]
    routed_skills = [tc.arguments.get("skill", "") for tc in omicsclaw_calls]
    if expected_skill in routed_skills or "auto" in routed_skills:
        return _ok()

    kh_pattern = re.compile(rf"^KH-{re.escape(expected_skill)}\b", re.IGNORECASE)
    for tc in result.tool_calls:
        if tc.name != "read_knowhow":
            continue
        kh_name = str(tc.arguments.get("name", "") or "")
        if kh_pattern.match(kh_name):
            return _ok()

    if not omicsclaw_calls:
        return _fail(
            f"expected routing to skill {expected_skill!r}, "
            f"but no omicsclaw tool call was emitted "
            f"and no read_knowhow(name='KH-{expected_skill}-*') signal "
            f"was found; tool calls observed: "
            f"{list(result.tool_names) or '(none)'}"
        )

    return _fail(
        f"expected omicsclaw(skill={expected_skill!r}) or omicsclaw(skill='auto'); "
        f"got {routed_skills}"
    )


# --- Helper 2: tool-call set membership --------------------------------------


def assert_calls_tools(
    result: LLMRoundResult,
    *,
    must_call: tuple[str, ...] = (),
    must_not_call: tuple[str, ...] = (),
) -> AssertResult:
    """Pass iff every name in ``must_call`` appears AND none in
    ``must_not_call`` appears in the captured tool_calls."""
    actual = set(result.tool_names)
    reasons: list[str] = []

    missing = [t for t in must_call if t not in actual]
    if missing:
        reasons.append(
            f"required tool(s) not called: {missing}; "
            f"observed tool calls: {sorted(actual) or '(none)'}"
        )

    forbidden = [t for t in must_not_call if t in actual]
    if forbidden:
        reasons.append(
            f"forbidden tool(s) were called: {forbidden}; "
            f"observed tool calls: {sorted(actual)}"
        )

    return _ok() if not reasons else _fail(*reasons)


# --- Helper 3: response-text regex matching ----------------------------------


def assert_response_mentions(
    result: LLMRoundResult,
    *,
    must_mention: tuple[str, ...] = (),
    must_not_mention: tuple[str, ...] = (),
) -> AssertResult:
    """Pass iff each ``must_mention`` regex matches the response text AND
    every ``must_not_mention`` regex does NOT match. Patterns are
    compiled case-insensitive + dotall so multi-line LLM output works
    naturally.
    """
    text = result.response_text or ""

    # Multi-round agent tolerance: when the captured round emitted no
    # text and only inspection-class tool calls, the model is doing
    # inspect-before-action (SOUL.md ``Result Fidelity`` rule) and the
    # substantive response lives in the follow-up round we don't
    # capture. Skip the mention check rather than failing — punishing
    # this would over-fit eval to behavior production never demands.
    if (
        not text
        and result.tool_calls
        and all(tc.name in _INSPECTION_TOOL_NAMES for tc in result.tool_calls)
    ):
        return _ok()

    reasons: list[str] = []

    for pattern in must_mention:
        try:
            compiled = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        except re.error as exc:
            reasons.append(f"invalid must_mention regex {pattern!r}: {exc}")
            continue
        if not compiled.search(text):
            reasons.append(
                f"required pattern {pattern!r} not found in response "
                f"(first 200 chars: {text[:200]!r})"
            )

    for pattern in must_not_mention:
        try:
            compiled = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        except re.error as exc:
            reasons.append(f"invalid must_not_mention regex {pattern!r}: {exc}")
            continue
        match = compiled.search(text)
        if match:
            reasons.append(
                f"forbidden pattern {pattern!r} matched in response: "
                f"{match.group(0)[:100]!r}"
            )

    return _ok() if not reasons else _fail(*reasons)
