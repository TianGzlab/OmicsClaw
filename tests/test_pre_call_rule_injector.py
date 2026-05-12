"""Phase 4 (Task 4.5) tests for the ``PreCallRuleInjector`` hook.

Pre-call rule injection is the third lazy-load mechanism (alongside
predicate-gated layers and the ``read_knowhow`` RAG tool). It fires at
tool-execution time: when the model dispatches a specific tool, a
backend-side injector prepends the relevant rule_text to the tool
result so the model sees the rule *just in time* without paying the
cost on every turn.

Used for:
- Engineering discipline (read first, smallest change, OWASP, no .sh)
  fires before ``file_edit`` / ``file_write`` / ``custom_analysis_execute``.
- Skill execution rule (lowercase method, canonical aliases, output/
  location) fires before ``omicsclaw``.
"""

from __future__ import annotations

import pytest

from omicsclaw.runtime.tool_execution_hooks import (
    PreCallRuleInjector,
    build_pre_call_rule_text,
)


def _eng_injector() -> PreCallRuleInjector:
    return PreCallRuleInjector(
        name="engineering_preamble",
        matches=lambda tool_name, _args: tool_name in ("file_edit", "file_write"),
        rule_text="ENG_RULE: read first; smallest change.",
    )


def _skill_injector() -> PreCallRuleInjector:
    return PreCallRuleInjector(
        name="skill_execution_preamble",
        matches=lambda tool_name, _args: tool_name == "omicsclaw",
        rule_text="SKILL_RULE: lowercase method.",
    )


def test_pre_call_rule_text_returns_match_for_single_injector() -> None:
    text = build_pre_call_rule_text(
        tool_name="file_edit",
        tool_args={"path": "foo.py"},
        injectors=(_eng_injector(),),
    )
    assert "ENG_RULE" in text


def test_pre_call_rule_text_concatenates_multiple_matches() -> None:
    """When multiple injectors match (rare but supported), their texts
    concatenate so the model sees every relevant rule before the tool
    result body."""
    eng = _eng_injector()
    extra = PreCallRuleInjector(
        name="extra_preamble",
        matches=lambda tool_name, _args: tool_name == "file_edit",
        rule_text="EXTRA_RULE: also relevant.",
    )
    text = build_pre_call_rule_text(
        tool_name="file_edit",
        tool_args={"path": "foo.py"},
        injectors=(eng, extra),
    )
    assert "ENG_RULE" in text
    assert "EXTRA_RULE" in text


def test_pre_call_rule_text_returns_empty_when_no_match() -> None:
    text = build_pre_call_rule_text(
        tool_name="file_read",
        tool_args={"path": "foo.py"},
        injectors=(_eng_injector(), _skill_injector()),
    )
    assert text == ""


def test_pre_call_rule_text_skips_injectors_with_other_tool() -> None:
    text = build_pre_call_rule_text(
        tool_name="omicsclaw",
        tool_args={"skill": "sc-de"},
        injectors=(_eng_injector(), _skill_injector()),
    )
    assert "SKILL_RULE" in text
    assert "ENG_RULE" not in text


def test_pre_call_rule_text_handles_match_predicate_exception() -> None:
    """A misbehaving ``matches`` callback must not break the chain — the
    bad injector is skipped, not propagated. Mirrors the fail-closed
    rule used by ContextLayerInjector predicates."""
    bad = PreCallRuleInjector(
        name="bad_match",
        matches=lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("synthetic")),
        rule_text="BAD",
    )
    text = build_pre_call_rule_text(
        tool_name="omicsclaw",
        tool_args={"skill": "sc-de"},
        injectors=(bad, _skill_injector()),
    )
    assert "BAD" not in text
    assert "SKILL_RULE" in text
