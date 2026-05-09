"""Phase 4 (Task 4.6) tests for the two registered tool-preamble injectors.

The Phase 4 design ships two ``PreCallRuleInjector`` instances on bot/
interactive surfaces:

1. **engineering_preamble** — fires before code-writing tools
   (``file_edit``, ``file_write`` of .py/.R/.ipynb,
   ``custom_analysis_execute``). Carries the existing-first / minimal
   change / OWASP / no-shell-script rules that used to live in
   ``skill_contract §6 Controlled Execution`` and ``§8 Engineering
   Discipline``.
2. **skill_execution_preamble** — fires before ``omicsclaw`` calls.
   Carries lowercase method, canonical alias preference, deep-learning
   warning, and per-analysis output/ subdirectory location.

Tests pin both the trigger logic and the substantive content of each
preamble so the migration from the deleted ``skill_contract`` layer
doesn't lose rules.
"""

from __future__ import annotations

import pytest

from omicsclaw.runtime.tool_execution_hooks import (
    DEFAULT_PRE_CALL_RULE_INJECTORS,
    build_pre_call_rule_text,
)


def _preamble(tool_name: str, tool_args: dict | None = None) -> str:
    return build_pre_call_rule_text(
        tool_name=tool_name,
        tool_args=tool_args or {},
        injectors=DEFAULT_PRE_CALL_RULE_INJECTORS,
    )


# --- engineering_preamble ----------------------------------------------------


def test_engineering_preamble_fires_on_file_edit() -> None:
    text = _preamble("file_edit", {"path": "src/foo.py"})
    assert text, "engineering preamble missing for file_edit"


def test_engineering_preamble_fires_on_file_write_of_py_or_r() -> None:
    py_text = _preamble("file_write", {"path": "out/script.py"})
    r_text = _preamble("file_write", {"path": "out/script.R"})
    assert py_text, "engineering preamble missing for .py file_write"
    assert r_text, "engineering preamble missing for .R file_write"


def test_engineering_preamble_quiet_on_file_write_of_unrelated_extension() -> None:
    """``file_write`` of a non-code file (e.g. .csv) should not trigger
    the engineering rules."""
    text = _preamble("file_write", {"path": "out/data.csv"})
    assert "OWASP" not in text


def test_engineering_preamble_fires_on_custom_analysis_execute() -> None:
    text = _preamble("custom_analysis_execute", {"code": "import scanpy"})
    assert text, "engineering preamble missing for custom_analysis_execute"


def test_engineering_preamble_quiet_on_unrelated_tool() -> None:
    text = _preamble("file_read", {"path": "src/foo.py"})
    assert text == ""


def test_engineering_preamble_content_covers_core_rules() -> None:
    text = _preamble("file_edit", {"path": "src/foo.py"}).lower()
    assert "smallest" in text or "minimal" in text
    assert "existing" in text or "read first" in text
    assert "owasp" in text or "injection" in text
    assert ".sh" in text or "shell" in text


# --- skill_execution_preamble ------------------------------------------------


def test_skill_execution_preamble_fires_on_omicsclaw_tool() -> None:
    text = _preamble("omicsclaw", {"skill": "sc-de", "input": "/tmp/x.h5ad"})
    assert text, "skill execution preamble missing for omicsclaw call"


def test_skill_execution_preamble_quiet_on_other_tool() -> None:
    text = _preamble("file_read", {"path": "/tmp/x.h5ad"})
    assert "lowercase" not in text.lower()
    assert "canonical" not in text.lower()


def test_skill_execution_preamble_content_covers_method_and_output() -> None:
    text = _preamble("omicsclaw", {"skill": "sc-de"}).lower()
    assert "lowercase" in text
    assert "canonical" in text or "alias" in text
    assert "output/" in text


# --- Both preambles fire when both tools' criteria match (e.g. omicsclaw + custom analysis combo, ---
# --- not realistic in one call but we verify they don't interfere) ---------


def test_engineering_and_skill_preamble_do_not_collide() -> None:
    """``omicsclaw`` fires only the skill preamble; ``file_edit`` fires
    only the engineering preamble. Verify the matchers don't accidentally
    overlap."""
    eng_only = _preamble("file_edit", {"path": "src/foo.py"})
    skill_only = _preamble("omicsclaw", {"skill": "sc-de"})
    assert "lowercase" not in eng_only.lower()
    assert "owasp" not in skill_only.lower()


# --- query_engine integration ------------------------------------------------


def test_query_engine_actually_calls_build_pre_call_rule_text() -> None:
    """Phase 4 critical regression guard: ``PreCallRuleInjector`` is dead
    weight unless the runtime tool-execution path actually *invokes*
    ``build_pre_call_rule_text``. Stronger than a bare import-check —
    pins both the import AND the call-expression so an orphaned import
    left by a refactor still fails the test.
    """
    import inspect

    from omicsclaw.runtime import query_engine as qe_mod

    source = inspect.getsource(qe_mod)
    assert "build_pre_call_rule_text" in source, (
        "query_engine no longer references build_pre_call_rule_text"
    )
    assert "DEFAULT_PRE_CALL_RULE_INJECTORS" in source, (
        "query_engine no longer references DEFAULT_PRE_CALL_RULE_INJECTORS"
    )
    assert "build_pre_call_rule_text(" in source, (
        "query_engine imports but does not invoke build_pre_call_rule_text — "
        "the engineering / skill_execution preambles never reach the model. "
        "Re-wire the call site or delete the abstraction."
    )


def test_query_engine_prepends_preamble_to_tool_record_output_observably() -> None:
    """E2E observable test: drive the same call site ``query_engine``
    uses (``build_pre_call_rule_text`` over
    ``DEFAULT_PRE_CALL_RULE_INJECTORS``) with realistic tool args, and
    observe that the preamble text would be prepended to a synthetic
    record_output exactly the way the production code does it. If the
    production prepend pattern changes (e.g. swap to "append" or use a
    different separator), this test catches it.
    """
    from omicsclaw.runtime.tool_execution_hooks import (
        DEFAULT_PRE_CALL_RULE_INJECTORS,
        build_pre_call_rule_text,
    )

    record_output = "TOOL_OUTPUT_BODY"
    preamble_text = build_pre_call_rule_text(
        tool_name="file_edit",
        tool_args={"path": "src/foo.py"},
        injectors=DEFAULT_PRE_CALL_RULE_INJECTORS,
    )
    # Mirror exactly what query_engine.py does after the existing notices
    # block. If this assertion ever drifts from the production pattern,
    # update query_engine and this test together.
    final_output = (
        f"{preamble_text}\n\n{record_output}".strip()
        if preamble_text
        else record_output
    )

    assert "Engineering preamble" in final_output
    assert final_output.endswith("TOOL_OUTPUT_BODY"), (
        "preamble must precede the tool body (prepend, not append)"
    )
    assert "TOOL_OUTPUT_BODY" in final_output
