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


def test_bot_run_skill_via_shared_runner_streams_lines_to_bot_logger(
    tmp_path, monkeypatch, caplog
):
    """The bot must subscribe to runner stdout/stderr callbacks so long
    skills produce visible operator-console logs in real time instead of
    going silent until completion."""
    import omicsclaw.core.skill_runner as runner_module

    out_dir = tmp_path / "bot_streaming_out"
    out_dir.mkdir()

    def fake_run_skill(skill_name=None, *, stdout_callback=None, stderr_callback=None, **kwargs):
        if stdout_callback is not None:
            stdout_callback("epoch 1/3")
            stdout_callback("epoch 2/3")
            stdout_callback("epoch 3/3")
        if stderr_callback is not None:
            stderr_callback("warning: synthetic")
        return {
            "skill": skill_name,
            "success": True,
            "exit_code": 0,
            "output_dir": str(out_dir),
            "files": [],
            "stdout": "epoch 1/3\nepoch 2/3\nepoch 3/3\n",
            "stderr": "warning: synthetic\n",
            "duration_seconds": 0.1,
            "method": None,
            "readme_path": "",
            "notebook_path": "",
        }

    monkeypatch.setattr(runner_module, "run_skill", fake_run_skill)

    with caplog.at_level("INFO", logger="omicsclaw.bot"):
        result = asyncio.run(
            core._run_skill_via_shared_runner(
                skill_key="literature",
                input_path=None,
                session_path=None,
                mode="demo",
                out_dir=out_dir,
            )
        )

    bot_messages = [r.getMessage() for r in caplog.records if r.name == "omicsclaw.bot"]
    assert any("epoch 1/3" in m for m in bot_messages), bot_messages
    assert any("epoch 2/3" in m for m in bot_messages), bot_messages
    assert any("epoch 3/3" in m for m in bot_messages), bot_messages
    assert any("warning: synthetic" in m for m in bot_messages), bot_messages
    assert result["success"] is True


def test_bot_run_skill_via_shared_runner_propagates_asyncio_cancel(tmp_path, monkeypatch):
    """If the bot's coroutine is cancelled (user disconnect, parent task
    killed), it must signal the runner so the worker thread / subprocess
    actually shuts down. Without this, ``run_skill`` keeps running long
    after the user is gone and continues to consume CPU/GPU.
    """
    import threading
    import omicsclaw.core.skill_runner as runner_module

    out_dir = tmp_path / "bot_cancel_out"
    out_dir.mkdir()
    captured_events: list[threading.Event] = []

    def fake_run_skill(skill_name=None, *, cancel_event=None, **kwargs):
        assert cancel_event is not None, (
            "bot adapter must pass a cancel_event so cancellation propagates"
        )
        captured_events.append(cancel_event)
        signaled = cancel_event.wait(timeout=10.0)
        return {
            "skill": skill_name,
            "success": not signaled,
            "exit_code": 137 if signaled else 0,
            "output_dir": str(out_dir),
            "files": [],
            "stdout": "",
            "stderr": "cancelled" if signaled else "",
            "duration_seconds": 0.1,
            "method": None,
            "readme_path": "",
            "notebook_path": "",
        }

    monkeypatch.setattr(runner_module, "run_skill", fake_run_skill)

    async def driver() -> None:
        task = asyncio.create_task(
            core._run_skill_via_shared_runner(
                skill_key="literature",
                input_path=None,
                session_path=None,
                mode="demo",
                out_dir=out_dir,
            )
        )
        # Wait until the worker thread actually entered run_skill.
        for _ in range(50):
            if captured_events:
                break
            await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(driver())

    assert captured_events, "fake_run_skill was never invoked"
    assert captured_events[0].is_set(), (
        "cancel_event was not set when the bot adapter's task was cancelled — "
        "the worker thread / subprocess would leak"
    )
