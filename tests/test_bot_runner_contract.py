from __future__ import annotations

import ast
import asyncio
import inspect
import sys
import types
from pathlib import Path

if "openai" not in sys.modules:
    sys.modules["openai"] = types.SimpleNamespace(
        AsyncOpenAI=object,
        APIError=Exception,
        OpenAIError=Exception,
    )

import bot.core as core


def _function_tree(func) -> ast.FunctionDef | ast.AsyncFunctionDef:
    source = inspect.getsource(func)
    module = ast.parse(source)
    node = module.body[0]
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    return node


def _calls_asyncio_subprocess(func) -> bool:
    tree = _function_tree(func)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = node.func
        if (
            isinstance(call, ast.Attribute)
            and call.attr == "create_subprocess_exec"
            and isinstance(call.value, ast.Name)
            and call.value.id == "asyncio"
        ):
            return True
    return False


def test_bot_normal_skill_paths_do_not_spawn_omicsclaw_run_subprocesses():
    assert not _calls_asyncio_subprocess(core._run_omics_skill_step)
    assert not _calls_asyncio_subprocess(core.execute_omicsclaw)


def test_execute_omicsclaw_uses_shared_runner_adapter(tmp_path, monkeypatch):
    out_dir = tmp_path / "bot_runner_out"
    out_dir.mkdir()
    (out_dir / "report.md").write_text("# Bot Runner\n\nOK\n", encoding="utf-8")
    (out_dir / "result.json").write_text('{"skill":"literature","summary":{},"data":{}}', encoding="utf-8")

    calls: list[dict] = []

    async def _fake_run(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "returncode": 0,
            "exit_code": 0,
            "out_dir": out_dir,
            "output_dir": str(out_dir),
            "stdout": "runner stdout",
            "stderr": "",
            "guidance_block": "",
            "error_text": "",
        }

    async def _unexpected_subprocess(*_args, **_kwargs):
        raise AssertionError("bot skill execution should not spawn omicsclaw.py run")

    monkeypatch.setattr(core, "_run_skill_via_shared_runner", _fake_run)
    monkeypatch.setattr(core.asyncio, "create_subprocess_exec", _unexpected_subprocess)
    monkeypatch.setattr(core, "_auto_capture_analysis", lambda *args, **kwargs: None)
    monkeypatch.setattr(core, "_auto_capture_dataset", lambda *args, **kwargs: None)

    result = asyncio.run(
        core.execute_omicsclaw(
            {"skill": "literature", "mode": "demo"},
            session_id=None,
            chat_id="bot-runner",
        )
    )

    assert calls
    assert calls[0]["skill_key"] == "literature"
    assert calls[0]["mode"] == "demo"
    assert "Bot Runner" in result
