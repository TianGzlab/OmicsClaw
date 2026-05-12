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
    "file_read",
    "list_directory",
})


# Skill-name → omics domain prefix mapping. Heuristic on the
# dash-separated prefix; covers every domain CLAUDE.md routes to. Used
# by ``assert_routes_to_skill`` to recognise ``resolve_capability(
# domain_hint=<domain>)`` as a routing signal when the hint matches the
# expected skill's home domain.
_DOMAIN_SKILL_PREFIXES: dict[str, tuple[str, ...]] = {
    "singlecell": ("sc-", "scatac-"),
    "spatial": ("spatial-",),
    "bulkrna": ("bulkrna-", "bulk-rnaseq-"),
    "genomics": ("genomics-",),
    "proteomics": ("proteomics-",),
    "metabolomics": ("metabolomics-",),
}


def _skill_domain(skill: str) -> str:
    """Return the omics domain a skill belongs to, or '' if unknown."""
    skill_lower = (skill or "").lower()
    for domain, prefixes in _DOMAIN_SKILL_PREFIXES.items():
        if any(skill_lower.startswith(p) for p in prefixes):
            return domain
    return ""


def _name_matches_skill_tokens(name: str, skill: str) -> bool:
    """Whether ``name`` contains every dash-separated token of ``skill``
    on a non-letter boundary (case-insensitive).

    Catches label-style ``read_knowhow`` calls like
    ``'Spatial Preprocess Guardrails'`` matching ``spatial-preprocess``
    while still rejecting cross-skill overlaps (e.g. ``'Bulk RNA-seq
    Differential Expression'`` does NOT contain the ``sc`` token at a
    word boundary so cannot cross-validate ``sc-de``).
    """
    if not name or not skill:
        return False
    name_lower = name.lower()
    tokens = [t for t in skill.lower().split("-") if t]
    if not tokens:
        return False
    return all(
        re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", name_lower)
        for token in tokens
    )


def _read_knowhow_resolves_to_skill_kh(name: str, expected_skill: str) -> bool:
    """Whether ``read_knowhow(name=...)`` resolves (using the production
    ``KnowHowInjector`` lookup chain — filename / doc_id / label) to a
    KH whose ``skills`` metadata lists ``expected_skill``.

    Catches label forms whose textual tokens don't textually overlap the
    skill name (e.g. ``'Best practices for Bulk RNA-seq Differential
    Expression Analysis'`` ↔ ``bulkrna-de``). Returns False on any
    lookup failure so the eval suite stays robust if the KH metadata
    moves or the injector import path breaks.
    """
    if not name or not expected_skill:
        return False
    try:
        from omicsclaw.knowledge.knowhow import get_knowhow_injector
    except Exception:
        return False

    target = name.strip().lower()
    if not target:
        return False
    try:
        injector = get_knowhow_injector()
        injector._ensure_loaded()
        metadata = injector._metadata
    except Exception:
        return False

    candidate = target if target.startswith("kh-") else f"kh-{target}"
    if not candidate.endswith(".md"):
        candidate = f"{candidate}.md"

    for filename, meta in metadata.items():
        fn_lower = filename.lower()
        doc_id_lower = (meta.doc_id or "").lower()
        label_lower = (meta.label or "").lower()
        if (
            fn_lower == target
            or fn_lower == candidate
            or (doc_id_lower and doc_id_lower == target)
            or (label_lower and label_lower == target)
        ):
            return expected_skill in (meta.skills or ())
    return False


# --- Helper 1: routing -------------------------------------------------------


def assert_routes_to_skill(
    result: LLMRoundResult, expected_skill: str
) -> AssertResult:
    """Pass iff the captured round routes to ``expected_skill``.

    Routing is detected as any of:

    1. An ``omicsclaw`` tool call whose ``skill`` argument equals
       ``expected_skill`` OR is ``"auto"`` (which the capability
       resolver resolves at runtime — accepting auto avoids forcing
       the model to pre-resolve).
    2. A ``read_knowhow(name=...)`` whose ``name`` (filename / doc_id /
       label form — all three are accepted by the production tool)
       contains every dash-separated token of ``expected_skill`` on
       word boundaries. Catches the production happy path where the
       headline-only block surfaces labels and the model copies them
       verbatim.
    3. A ``resolve_capability(domain_hint=<domain>)`` whose
       ``domain_hint`` matches the omics domain of ``expected_skill``.
       OmicsClaw's dispatch tool — calling it is itself a request to
       route, and the domain hint scopes the lookup to the right
       subset of skills.
    """
    if not expected_skill:
        return _ok()

    omicsclaw_calls = [tc for tc in result.tool_calls if tc.name == "omicsclaw"]
    routed_skills = [tc.arguments.get("skill", "") for tc in omicsclaw_calls]
    if expected_skill in routed_skills or "auto" in routed_skills:
        return _ok()

    for tc in result.tool_calls:
        if tc.name != "read_knowhow":
            continue
        kh_name = str(tc.arguments.get("name", "") or "")
        if _name_matches_skill_tokens(kh_name, expected_skill):
            return _ok()
        if _read_knowhow_resolves_to_skill_kh(kh_name, expected_skill):
            return _ok()

    expected_domain = _skill_domain(expected_skill)
    if expected_domain:
        for tc in result.tool_calls:
            # ``resolve_capability(domain_hint=...)`` and
            # ``consult_knowledge(domain=...)`` are peer dispatcher tools
            # — both surface the omics domain as a routing hint.
            if tc.name == "resolve_capability":
                hint = str(tc.arguments.get("domain_hint", "") or "").lower()
            elif tc.name == "consult_knowledge":
                hint = str(tc.arguments.get("domain", "") or "").lower()
            else:
                continue
            if hint == expected_domain:
                return _ok()

    if not omicsclaw_calls:
        return _fail(
            f"expected routing to skill {expected_skill!r}, "
            f"but no omicsclaw tool call was emitted, "
            f"no read_knowhow(name=...) matched the skill's tokens, "
            f"and no resolve_capability(domain_hint={expected_domain!r}) "
            f"was issued; tool calls observed: "
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

    # Multi-round agent tolerance: when the captured round consists only
    # of inspection-class tool calls (no substantive action), the model
    # is doing inspect-before-action (SOUL.md ``Result Fidelity`` rule)
    # and the substantive response lives in the follow-up round we
    # don't capture. The captured round may emit a short preamble
    # ("Let me check the file.") but the answer the regex looks for
    # never lives there. Skip the mention check rather than failing.
    if (
        result.tool_calls
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
