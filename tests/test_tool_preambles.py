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
