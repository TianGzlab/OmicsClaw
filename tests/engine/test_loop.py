"""Smoke tests for ``omicsclaw.engine.run_engine_loop``.

Full end-to-end coverage lives in ``tests/bot/test_agent_loop.py``
(via the bot wirer landed in 6c). The tests here focus on the
contract the engine itself owns: the LLM-not-configured early
return, and the helper string functions used to compose the
system prompt.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from omicsclaw.engine import (
    EngineDependencies,
    LLM_NOT_CONFIGURED_MESSAGE,
    run_engine_loop,
)
from omicsclaw.engine.loop import (
    _maybe_append_caller_addition,
    _maybe_append_mode_hint,
)


def _make_deps(**overrides) -> EngineDependencies:
    """Build a full EngineDependencies with minimal sentinel values."""
    field_names = {f.name for f in dataclasses.fields(EngineDependencies)}
    defaults = {name: None for name in field_names}
    defaults["omicsclaw_model"] = "test-model"
    defaults["llm_provider_name"] = "test-provider"
    defaults["omicsclaw_dir"] = "/tmp/oc-test"
    defaults["max_history"] = 80
    defaults["max_history_chars"] = None
    defaults["max_conversations"] = 200
    defaults["skill_aliases"] = ()
    defaults["deep_learning_methods"] = frozenset()
    defaults.update(overrides)
    return EngineDependencies(**defaults)


def test_returns_setup_prompt_when_llm_is_none() -> None:
    """If bot.core.llm is None at request time, the engine returns
    a setup-instructions message instead of raising. This is the
    contract the bot has relied on since core.py was carved up."""
    deps = _make_deps(llm=None)

    result = asyncio.run(
        run_engine_loop(
            deps=deps,
            chat_id="chat-1",
            user_content="hello",
        )
    )

    assert result == LLM_NOT_CONFIGURED_MESSAGE
    assert "LLM is not configured" in result
    assert "LLM_API_KEY" in result


class TestMaybeAppendCallerAddition:
    def test_no_op_for_empty(self) -> None:
        assert _maybe_append_caller_addition("base", "") == "base"

    def test_strips_added_section(self) -> None:
        assert (
            _maybe_append_caller_addition("base", "  extra  ") == "base\n\nextra"
        )

    def test_strips_trailing_whitespace_on_base(self) -> None:
        assert (
            _maybe_append_caller_addition("base   \n\n", "extra")
            == "base\n\nextra"
        )


class TestMaybeAppendModeHint:
    def test_unknown_mode_is_no_op(self) -> None:
        assert _maybe_append_mode_hint("base", "wat") == "base"

    def test_ask_mode_is_no_op(self) -> None:
        # "ask" is the implicit default — emitting a mode hint for it
        # would just add noise to every system prompt.
        assert _maybe_append_mode_hint("base", "ask") == "base"

    def test_empty_mode_is_no_op(self) -> None:
        assert _maybe_append_mode_hint("base", "") == "base"

    def test_code_mode_appends_section(self) -> None:
        result = _maybe_append_mode_hint("base", "code")
        assert "## Mode" in result
        assert "code mode" in result
        assert result.startswith("base")

    def test_plan_mode_appends_section(self) -> None:
        result = _maybe_append_mode_hint("base", "plan")
        assert "## Mode" in result
        assert "plan mode" in result


def test_max_tool_iterations_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The constant is read from env at import time. Reimporting
    the module after setting the env var should yield the new value
    — proves the engine isn't ignoring the user's override."""
    import importlib

    monkeypatch.setenv("OMICSCLAW_MAX_TOOL_ITERATIONS", "42")
    import omicsclaw.engine.loop as loop_module

    reloaded = importlib.reload(loop_module)
    assert reloaded.MAX_TOOL_ITERATIONS == 42

    # Restore the default so other tests in this session see the
    # original module-level value (importlib.reload mutates the
    # actual module object, so we reload again with the env unset).
    monkeypatch.delenv("OMICSCLAW_MAX_TOOL_ITERATIONS", raising=False)
    importlib.reload(loop_module)
