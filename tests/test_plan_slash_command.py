"""Tests for the /plan slash command in the bot path.

The /plan command shows the canonical plan.md from the active pipeline
workspace (or the bot's general workspace when set). It does not invoke the
LLM — it's a deterministic file read.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import types

import pytest


@pytest.fixture
def bot_core(monkeypatch):
    if "httpx" not in sys.modules:
        httpx_stub = types.ModuleType("httpx")

        class _StubHTTPError(Exception):
            pass

        httpx_stub.HTTPError = _StubHTTPError  # type: ignore[attr-defined]
        httpx_stub.ConnectError = _StubHTTPError  # type: ignore[attr-defined]
        httpx_stub.TimeoutException = _StubHTTPError  # type: ignore[attr-defined]
        httpx_stub.get = lambda *_, **__: None  # type: ignore[attr-defined]
        sys.modules["httpx"] = httpx_stub
    for stub_name in ("openai", "tiktoken"):
        if stub_name not in sys.modules:
            sys.modules[stub_name] = types.ModuleType(stub_name)
    if "openai" in sys.modules and not hasattr(sys.modules["openai"], "AsyncOpenAI"):
        class _FakeAsyncOpenAI:
            def __init__(self, *_, **__):
                pass

        class _FakeAPIError(Exception):
            pass

        sys.modules["openai"].AsyncOpenAI = _FakeAsyncOpenAI  # type: ignore[attr-defined]
        sys.modules["openai"].APIError = _FakeAPIError  # type: ignore[attr-defined]
    try:
        return importlib.import_module("bot.core")
    except ImportError as exc:
        pytest.skip(f"bot.core unavailable: {exc}")


def test_plan_returns_file_when_pipeline_workspace_has_plan(bot_core, tmp_path):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text(
        "# Pipeline Plan\n\n## Stage 1\n- step a\n- step b\n",
        encoding="utf-8",
    )

    result = asyncio.run(
        bot_core.llm_tool_loop(
            "plan-chat",
            "/plan",
            pipeline_workspace=str(tmp_path),
        )
    )

    assert "Pipeline Plan" in result
    assert "Stage 1" in result


def test_plan_falls_back_to_workspace(bot_core, tmp_path):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Workspace Plan\n", encoding="utf-8")

    result = asyncio.run(
        bot_core.llm_tool_loop(
            "plan-chat-2",
            "/plan",
            workspace=str(tmp_path),
        )
    )
    assert "Workspace Plan" in result


def test_plan_returns_helpful_message_when_no_plan(bot_core, tmp_path):
    result = asyncio.run(
        bot_core.llm_tool_loop(
            "plan-chat-3",
            "/plan",
            pipeline_workspace=str(tmp_path),
        )
    )
    # No plan.md exists — handler must say so without calling the LLM
    assert "no plan" in result.lower() or "not found" in result.lower()


def test_plan_truncates_very_long_plan(bot_core, tmp_path):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Plan\n\n" + ("line\n" * 5000), encoding="utf-8")

    result = asyncio.run(
        bot_core.llm_tool_loop(
            "plan-chat-4",
            "/plan",
            pipeline_workspace=str(tmp_path),
        )
    )

    # Output should be capped — never dump the entire 5000-line file into chat.
    assert len(result) < 12000
    assert "truncated" in result.lower()
