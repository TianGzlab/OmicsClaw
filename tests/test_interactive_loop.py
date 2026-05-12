from __future__ import annotations

import inspect
import io
import logging
import os
import subprocess
import sys
from types import ModuleType
from types import SimpleNamespace

import pytest
from rich.console import Console

from omicsclaw.core.registry import OmicsRegistry
from omicsclaw.interactive import interactive
from omicsclaw.interactive._session_state import SessionState
from omicsclaw.interactive._session_command_support import (
    SessionCommandView,
    SessionListEntry,
    SessionListView,
)


def test_interactive_import_does_not_require_graph_memory_dependencies():
    env = dict(os.environ)
    env["OMICSCLAW_MEMORY_ENABLED"] = "false"
    code = """
import builtins

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "sqlalchemy" or name.startswith("sqlalchemy."):
        raise ModuleNotFoundError("No module named 'sqlalchemy'")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import omicsclaw.interactive.interactive
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(interactive._OMICSCLAW_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


@pytest.mark.asyncio
async def test_stream_llm_response_uses_explicit_workspace_context(monkeypatch):
    captured: dict[str, object] = {}
    output = io.StringIO()

    async def _fake_llm_tool_loop(
        conversation_id,
        user_text,
        *,
        user_id="",
        platform="",
        plan_context="",
        workspace="",
        pipeline_workspace="",
        mcp_servers=(),
        output_style="",
        on_tool_call=None,
        on_tool_result=None,
        on_stream_content=None,
    ):
        captured.update(
            {
                "conversation_id": conversation_id,
                "user_text": user_text,
                "plan_context": plan_context,
                "workspace": workspace,
                "pipeline_workspace": pipeline_workspace,
                "mcp_servers": tuple(mcp_servers),
                "output_style": output_style,
            }
        )
        core_module.conversations[conversation_id] = [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": "I am OmicsClaw."},
        ]
        if on_stream_content is not None:
            await on_stream_content("I am ")
            await on_stream_content("OmicsClaw.")
        return "I am OmicsClaw."

    core_module = ModuleType("bot.core")
    core_module.conversations = {}
    core_module._conversation_access = {}
    core_module.get_usage_snapshot = lambda: {}
    core_module.llm_tool_loop = _fake_llm_tool_loop

    bot_package = ModuleType("bot")
    bot_package.core = core_module

    monkeypatch.setitem(sys.modules, "bot", bot_package)
    monkeypatch.setitem(sys.modules, "bot.core", core_module)
    monkeypatch.setattr(interactive, "list_mcp_servers", lambda: [])
    monkeypatch.setattr(interactive, "console", Console(file=output, force_terminal=False))

    messages = [{"role": "user", "content": "介绍你自己"}]
    result = await interactive._stream_llm_response(
        messages,
        workspace_dir="/tmp/workspace",
        pipeline_workspace="/tmp/pipeline",
        output_style="scientific-brief",
    )

    assert result == "I am OmicsClaw."
    assert captured["user_text"] == "介绍你自己"
    assert captured["plan_context"] == ""
    assert captured["workspace"] == "/tmp/workspace"
    assert captured["pipeline_workspace"] == "/tmp/pipeline"
    assert captured["output_style"] == "scientific-brief"
    rendered = output.getvalue()
    assert rendered.count("I am OmicsClaw.") == 1
    assert messages == [
        {"role": "user", "content": "介绍你自己"},
        {"role": "assistant", "content": "I am OmicsClaw."},
    ]


def test_init_llm_does_not_force_registry_load(monkeypatch):
    calls: list[tuple[tuple, dict]] = []
    real_load_all = OmicsRegistry.load_all

    def spy(self, *args, **kwargs):
        calls.append((args, kwargs))
        return real_load_all(self, *args, **kwargs)

    for name in (
        "bot.core",
        "omicsclaw.runtime.context_assembler",
        "omicsclaw.runtime.context_layers",
    ):
        sys.modules.pop(name, None)

    monkeypatch.setattr(OmicsRegistry, "load_all", spy)
    monkeypatch.setenv("OMICSCLAW_MEMORY_ENABLED", "false")
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("OMICSCLAW_MODEL", "test-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")

    model, provider = interactive._init_llm({})

    assert model == "test-model"
    assert provider == "custom"
    assert calls == []


def test_init_llm_prefers_explicit_config_over_environment(monkeypatch):
    captured: dict[str, str | None] = {}
    core_module = ModuleType("bot.core")
    core_module.OMICSCLAW_MODEL = "config-model"
    core_module.LLM_PROVIDER_NAME = "custom"

    def _init(**kwargs):
        captured.update(kwargs)
        core_module.OMICSCLAW_MODEL = str(kwargs["model"])
        core_module.LLM_PROVIDER_NAME = str(kwargs["provider"])

    core_module.init = _init
    bot_package = ModuleType("bot")
    bot_package.core = core_module

    monkeypatch.setitem(sys.modules, "bot", bot_package)
    monkeypatch.setitem(sys.modules, "bot.core", core_module)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "env-key")
    monkeypatch.setenv("OMICSCLAW_MODEL", "env-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://env.example/v1")

    model, provider = interactive._init_llm(
        {
            "provider": "custom",
            "api_key": "config-key",
            "model": "config-model",
            "base_url": "https://config.example/v1",
        }
    )

    assert captured == {
        "api_key": "config-key",
        "base_url": "https://config.example/v1",
        "model": "config-model",
        "provider": "custom",
    }
    assert model == "config-model"
    assert provider == "custom"


def test_configure_cli_loggers_falls_back_to_error_for_invalid_env(monkeypatch):
    monkeypatch.setenv("OMICSCLAW_LOG_LEVEL", "INF0")

    interactive._configure_cli_loggers()

    assert logging.getLogger("openai").level == logging.ERROR


@pytest.mark.asyncio
async def test_single_shot_passes_cli_model_and_provider_to_init(monkeypatch):
    captured: dict[str, str] = {}

    def _fake_init(config):
        captured.update(config)
        return "cli-model", "custom"

    async def _fake_stream_response(messages, **kwargs):
        messages.append({"role": "assistant", "content": "OK"})
        return "OK"

    async def _fake_save_session(*args, **kwargs):
        return None

    monkeypatch.setattr(interactive, "_init_llm", _fake_init)
    monkeypatch.setattr(interactive, "_stream_llm_response", _fake_stream_response)
    monkeypatch.setattr(interactive, "save_session", _fake_save_session)
    monkeypatch.setattr(
        interactive,
        "console",
        Console(file=io.StringIO(), force_terminal=False),
    )

    await interactive._single_shot(
        prompt="Say OK",
        workspace_dir="/tmp/workspace",
        model="cli-model",
        provider="custom",
        config={"base_url": "https://config.example/v1"},
    )

    assert captured["model"] == "cli-model"
    assert captured["provider"] == "custom"
    assert captured["base_url"] == "https://config.example/v1"


@pytest.mark.asyncio
async def test_stream_llm_response_formats_markdown_for_cli(monkeypatch):
    output = io.StringIO()

    async def _fake_llm_tool_loop(
        conversation_id,
        user_text,
        **kwargs,
    ):
        core_module.conversations[conversation_id] = [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": "**空间转录组学**"},
        ]
        on_stream_content = kwargs.get("on_stream_content")
        if on_stream_content is not None:
            await on_stream_content("**空间")
            await on_stream_content("转录组学**")
        return "**空间转录组学**"

    core_module = ModuleType("bot.core")
    core_module.conversations = {}
    core_module._conversation_access = {}
    core_module.get_usage_snapshot = lambda: {}
    core_module.llm_tool_loop = _fake_llm_tool_loop

    bot_package = ModuleType("bot")
    bot_package.core = core_module

    monkeypatch.setitem(sys.modules, "bot", bot_package)
    monkeypatch.setitem(sys.modules, "bot.core", core_module)
    monkeypatch.setattr(interactive, "list_mcp_servers", lambda: [])
    monkeypatch.setattr(interactive, "console", Console(file=output, force_terminal=False))

    await interactive._stream_llm_response(
        [{"role": "user", "content": "介绍空间转录组学"}],
        workspace_dir="/tmp/workspace",
    )

    rendered = output.getvalue()
    assert "空间转录组学" in rendered
    assert "**空间转录组学**" not in rendered
    assert rendered.count("空间转录组学") == 1


@pytest.mark.asyncio
async def test_stream_llm_response_passes_plan_context(monkeypatch):
    captured: dict[str, object] = {}
    output = io.StringIO()

    async def _fake_llm_tool_loop(
        conversation_id,
        user_text,
        **kwargs,
    ):
        captured["plan_context"] = kwargs.get("plan_context", "")
        core_module.conversations[conversation_id] = [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": "Plan-aware reply."},
        ]
        on_stream_content = kwargs.get("on_stream_content")
        if on_stream_content is not None:
            await on_stream_content("Plan-aware reply.")
        return "Plan-aware reply."

    core_module = ModuleType("bot.core")
    core_module.conversations = {}
    core_module._conversation_access = {}
    core_module.get_usage_snapshot = lambda: {}
    core_module.llm_tool_loop = _fake_llm_tool_loop

    bot_package = ModuleType("bot")
    bot_package.core = core_module

    monkeypatch.setitem(sys.modules, "bot", bot_package)
    monkeypatch.setitem(sys.modules, "bot.core", core_module)
    monkeypatch.setattr(interactive, "list_mcp_servers", lambda: [])
    monkeypatch.setattr(interactive, "console", Console(file=output, force_terminal=False))

    await interactive._stream_llm_response(
        [{"role": "user", "content": "按计划继续"}],
        plan_context="## Active Plan Mode\n\n- Status: approved",
        workspace_dir="/tmp/workspace",
    )

    assert captured["plan_context"] == "## Active Plan Mode\n\n- Status: approved"


@pytest.mark.asyncio
async def test_handle_resume_falls_back_to_session_search_for_unique_match(monkeypatch):
    calls: list[str] = []
    applied: list[SessionCommandView] = []
    output = io.StringIO()

    async def _build_resume(target_id: str) -> SessionCommandView:
        calls.append(target_id)
        if target_id == "brain":
            return SessionCommandView(
                output_text="Session 'brain' not found.",
                success=False,
            )
        assert target_id == "abc12345"
        return SessionCommandView(
            output_text="Resumed session: abc12345",
            success=True,
            session_id="abc12345",
            render_as_markup=True,
        )

    async def _build_session_list(limit: int = 20, *, query: str = "") -> SessionListView:
        assert limit == 20
        assert query == "brain"
        return SessionListView(
            entries=[SessionListEntry(session_id="abc12345", title="Brain Visium")]
        )

    monkeypatch.setattr(interactive, "build_resume_session_command_view", _build_resume)
    monkeypatch.setattr(interactive, "build_session_list_view", _build_session_list)
    monkeypatch.setattr(
        interactive,
        "_apply_session_command_view",
        lambda state, view: applied.append(view),
    )
    monkeypatch.setattr(interactive, "console", Console(file=output, force_terminal=False))

    await interactive._handle_resume(
        "brain",
        SessionState(session_id="current", workspace_dir="/tmp", ui_backend="cli"),
    )

    assert calls == ["brain", "abc12345"]
    assert [view.session_id for view in applied] == ["abc12345"]


def test_pipeline_snapshot_exists_uses_pipeline_workspace_resolver(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        interactive,
        "resolve_pipeline_workspace",
        lambda explicit, fallback: (
            captured.update({"explicit": explicit, "fallback": fallback}) or "/tmp/resolved"
        ),
    )
    monkeypatch.setattr(
        interactive,
        "load_pipeline_workspace_snapshot",
        lambda workspace: SimpleNamespace(
            has_pipeline_state=False,
            plan_path=SimpleNamespace(exists=lambda: True),
            todos_path=SimpleNamespace(exists=lambda: False),
        ),
    )

    assert interactive._pipeline_snapshot_exists(
        None,
        workspace_fallback="/tmp/workspace",
    ) is True
    assert captured == {"explicit": None, "fallback": "/tmp/workspace"}


@pytest.mark.asyncio
async def test_stream_llm_response_formats_sectioned_markdown_lists(monkeypatch):
    output = io.StringIO()

    markdown_text = """**数据检查结果：**
- 数据形状：428个细胞 × 25,753个基因
- 空间坐标：已找到（obsm['spatial']）
- 矩阵类型：只有X矩阵，没有layers，需要验证是否为log归一化表达

**根据空间SVG分析的科学约束：**
1. **矩阵假设检查**：Moran's I方法适用于log归一化表达数据，而SPARK-X、SpatialDE、FlashS等方法更适合原始计数数据
2. **方法选择**：对于这个中等规模的数据集（428个细胞），Moran's I是一个很好的基线方法
3. **参数解释**：需要明确说明关键参数"""

    async def _fake_llm_tool_loop(
        conversation_id,
        user_text,
        **kwargs,
    ):
        core_module.conversations[conversation_id] = [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": markdown_text},
        ]
        on_stream_content = kwargs.get("on_stream_content")
        if on_stream_content is not None:
            await on_stream_content(markdown_text)
        return markdown_text

    core_module = ModuleType("bot.core")
    core_module.conversations = {}
    core_module._conversation_access = {}
    core_module.get_usage_snapshot = lambda: {}
    core_module.llm_tool_loop = _fake_llm_tool_loop

    bot_package = ModuleType("bot")
    bot_package.core = core_module

    monkeypatch.setitem(sys.modules, "bot", bot_package)
    monkeypatch.setitem(sys.modules, "bot.core", core_module)
    monkeypatch.setattr(interactive, "list_mcp_servers", lambda: [])
    monkeypatch.setattr(interactive, "console", Console(file=output, force_terminal=False))

    await interactive._stream_llm_response(
        [{"role": "user", "content": "检查数据并给出约束"}],
        workspace_dir="/tmp/workspace",
    )

    rendered = output.getvalue()
    assert "数据检查结果：" in rendered
    assert "根据空间SVG分析的科学约束：" in rendered
    assert "- 数据形状：428个细胞 × 25,753个基因" in rendered
    assert "- 空间坐标：已找到（obsm['spatial']）" in rendered
    assert "1. 矩阵假设检查：Moran's I方法适用于log归一化表达数据" in rendered
    assert "2. 方法选择：对于这个中等规模的数据集（428个细胞）" in rendered
    assert "3. 参数解释：需要明确说明关键参数" in rendered
    assert "**" not in rendered


@pytest.mark.asyncio
async def test_stream_llm_response_separates_tool_log_from_response(monkeypatch):
    output = io.StringIO()

    async def _fake_llm_tool_loop(
        conversation_id,
        user_text,
        **kwargs,
    ):
        core_module.conversations[conversation_id] = [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": "Analysis ready."},
        ]
        on_tool_call = kwargs.get("on_tool_call")
        on_tool_result = kwargs.get("on_tool_result")
        on_stream_content = kwargs.get("on_stream_content")
        if on_tool_call is not None:
            maybe = on_tool_call("inspect_data", {"path": "sample.h5ad"})
            if inspect.isawaitable(maybe):
                await maybe
        if on_tool_result is not None:
            maybe = on_tool_result("inspect_data", "rows: 10\ncols: 5")
            if inspect.isawaitable(maybe):
                await maybe
        if on_stream_content is not None:
            await on_stream_content("Analysis ready.")
        return "Analysis ready."

    core_module = ModuleType("bot.core")
    core_module.conversations = {}
    core_module._conversation_access = {}
    core_module.get_usage_snapshot = lambda: {}
    core_module.llm_tool_loop = _fake_llm_tool_loop

    bot_package = ModuleType("bot")
    bot_package.core = core_module

    monkeypatch.setitem(sys.modules, "bot", bot_package)
    monkeypatch.setitem(sys.modules, "bot.core", core_module)
    monkeypatch.setattr(interactive, "list_mcp_servers", lambda: [])
    monkeypatch.setattr(interactive, "console", Console(file=output, force_terminal=False))

    await interactive._stream_llm_response(
        [{"role": "user", "content": "检查这个数据集"}],
        workspace_dir="/tmp/workspace",
    )

    rendered = output.getvalue()
    assert "TOOL LOG" in rendered
    assert "CALL #1  inspect_data" in rendered
    assert "DONE #1  rows: 10 cols: 5" in rendered
    assert "RESPONSE" in rendered
    assert rendered.count("Analysis ready.") == 1


@pytest.mark.asyncio
async def test_stream_llm_response_does_not_repeat_final_text_after_tool_interlude(monkeypatch):
    output = io.StringIO()

    async def _fake_llm_tool_loop(
        conversation_id,
        user_text,
        **kwargs,
    ):
        core_module.conversations[conversation_id] = [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": "Final answer."},
        ]
        on_tool_call = kwargs.get("on_tool_call")
        on_tool_result = kwargs.get("on_tool_result")
        on_stream_content = kwargs.get("on_stream_content")
        if on_stream_content is not None:
            await on_stream_content("Let me inspect that first.")
        if on_tool_call is not None:
            maybe = on_tool_call("inspect_data", {"path": "sample.h5ad"})
            if inspect.isawaitable(maybe):
                await maybe
        if on_tool_result is not None:
            maybe = on_tool_result("inspect_data", "preview ok")
            if inspect.isawaitable(maybe):
                await maybe
        if on_stream_content is not None:
            await on_stream_content("Final answer.")
        return "Final answer."

    core_module = ModuleType("bot.core")
    core_module.conversations = {}
    core_module._conversation_access = {}
    core_module.get_usage_snapshot = lambda: {}
    core_module.llm_tool_loop = _fake_llm_tool_loop

    bot_package = ModuleType("bot")
    bot_package.core = core_module

    monkeypatch.setitem(sys.modules, "bot", bot_package)
    monkeypatch.setitem(sys.modules, "bot.core", core_module)
    monkeypatch.setattr(interactive, "list_mcp_servers", lambda: [])
    monkeypatch.setattr(interactive, "console", Console(file=output, force_terminal=False))

    await interactive._stream_llm_response(
        [{"role": "user", "content": "帮我分析"}],
        workspace_dir="/tmp/workspace",
    )

    rendered = output.getvalue()
    assert "TOOL LOG" in rendered
    assert "CALL #1  inspect_data" in rendered
    assert "RESPONSE CONTINUES" in rendered
    assert rendered.count("Final answer.") == 1


@pytest.mark.asyncio
async def test_stream_llm_response_marks_followup_tool_batches_as_updates(monkeypatch):
    output = io.StringIO()

    async def _fake_llm_tool_loop(
        conversation_id,
        user_text,
        **kwargs,
    ):
        core_module.conversations[conversation_id] = [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": "Done."},
        ]
        on_tool_call = kwargs.get("on_tool_call")
        on_tool_result = kwargs.get("on_tool_result")
        on_stream_content = kwargs.get("on_stream_content")

        if on_tool_call is not None:
            maybe = on_tool_call("inspect_data", {"path": "sample.h5ad"})
            if inspect.isawaitable(maybe):
                await maybe
        if on_tool_result is not None:
            maybe = on_tool_result("inspect_data", "preview one")
            if inspect.isawaitable(maybe):
                await maybe
        if on_stream_content is not None:
            await on_stream_content("Partial response.")
        if on_tool_call is not None:
            maybe = on_tool_call("consult_knowledge", {"query": "marker genes"})
            if inspect.isawaitable(maybe):
                await maybe
        if on_tool_result is not None:
            maybe = on_tool_result("consult_knowledge", "preview two")
            if inspect.isawaitable(maybe):
                await maybe
        if on_stream_content is not None:
            await on_stream_content("Done.")
        return "Done."

    core_module = ModuleType("bot.core")
    core_module.conversations = {}
    core_module._conversation_access = {}
    core_module.get_usage_snapshot = lambda: {}
    core_module.llm_tool_loop = _fake_llm_tool_loop

    bot_package = ModuleType("bot")
    bot_package.core = core_module

    monkeypatch.setitem(sys.modules, "bot", bot_package)
    monkeypatch.setitem(sys.modules, "bot.core", core_module)
    monkeypatch.setattr(interactive, "list_mcp_servers", lambda: [])
    monkeypatch.setattr(interactive, "console", Console(file=output, force_terminal=False))

    await interactive._stream_llm_response(
        [{"role": "user", "content": "继续分析"}],
        workspace_dir="/tmp/workspace",
    )

    rendered = output.getvalue()
    assert "TOOL LOG" in rendered
    assert "TOOL UPDATE" in rendered
    assert "CALL #1  inspect_data" in rendered
    assert "DONE #1  preview one" in rendered
    assert "CALL #2  consult_knowledge" in rendered
    assert "DONE #2  preview two" in rendered
    assert "RESPONSE CONTINUES" in rendered
    assert rendered.count("Done.") == 1


def test_handle_doctor_applies_shared_diagnostics_view(monkeypatch):
    captured: dict[str, object] = {}
    state = SessionState(
        session_id="doctor",
        workspace_dir="/tmp/workspace",
        ui_backend="cli",
    )

    monkeypatch.setattr(interactive, "_active_pipeline_workspace", lambda state: "/tmp/pipeline")

    def _fake_build_doctor_command_view(**kwargs):
        captured["kwargs"] = kwargs
        return SessionCommandView("Doctor Report", render_as_markup=True)

    monkeypatch.setattr(interactive, "build_doctor_command_view", _fake_build_doctor_command_view)
    monkeypatch.setattr(
        interactive,
        "_apply_session_command_view",
        lambda state, view: captured.update({"state": state, "view": view}),
    )

    interactive._handle_doctor(state)

    assert captured["kwargs"]["workspace_dir"] == "/tmp/workspace"
    assert captured["kwargs"]["pipeline_workspace"] == "/tmp/pipeline"
    assert captured["view"].output_text == "Doctor Report"


def test_handle_context_passes_session_state_to_shared_builder(monkeypatch):
    captured: dict[str, object] = {}
    state = SessionState(
        session_id="ctx",
        workspace_dir="/tmp/workspace",
        ui_backend="cli",
        session_metadata={"active_style": "teaching"},
        messages=[{"role": "user", "content": "inspect sample.h5ad"}],
    )

    monkeypatch.setattr(interactive, "_active_pipeline_workspace", lambda state: "/tmp/pipeline")
    monkeypatch.setattr(interactive, "_active_output_style", lambda state: "teaching")
    monkeypatch.setattr(interactive, "_configured_mcp_server_names", lambda: ("mcp-a",))

    def _fake_build_context_command_view(arg, **kwargs):
        captured["arg"] = arg
        captured["kwargs"] = kwargs
        return SessionCommandView("Context Report", render_as_markup=True)

    monkeypatch.setattr(interactive, "build_context_command_view", _fake_build_context_command_view)
    monkeypatch.setattr(
        interactive,
        "_apply_session_command_view",
        lambda state, view: captured.update({"state": state, "view": view}),
    )

    interactive._handle_context("show me", state)

    assert captured["arg"] == "show me"
    assert captured["kwargs"]["workspace_dir"] == "/tmp/workspace"
    assert captured["kwargs"]["pipeline_workspace"] == "/tmp/pipeline"
    assert captured["kwargs"]["output_style"] == "teaching"
    assert captured["kwargs"]["mcp_servers"] == ("mcp-a",)


def test_handle_usage_applies_shared_usage_view(monkeypatch):
    captured: dict[str, object] = {}
    state = SessionState(session_id="demo", workspace_dir="/tmp", ui_backend="cli")

    monkeypatch.setattr(
        interactive,
        "build_usage_command_view",
        lambda: SessionCommandView("Usage Report", render_as_markup=True),
    )
    monkeypatch.setattr(
        interactive,
        "_apply_session_command_view",
        lambda state, view: captured.update({"state": state, "view": view}),
    )

    interactive._handle_usage(state)

    assert captured["state"] is state
    assert captured["view"].output_text == "Usage Report"
