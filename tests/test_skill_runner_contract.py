from __future__ import annotations

import importlib
import inspect
import json
import sys
import textwrap
import threading
import time
from pathlib import Path


def _install_fake_skills(monkeypatch, skills: dict, domains: dict | None = None) -> None:
    """Inject fake skills/domains into the live registry for the duration of a test.

    The runner no longer caches ``SKILLS`` / ``DOMAINS`` at module-import time
    (so that ``registry.reload()`` actually takes effect for downstream
    callers). Tests therefore patch ``registry.skills`` / ``registry.domains``
    directly and freeze ``_loaded`` so that any internal
    ``ensure_registry_loaded()`` calls become a no-op rather than rescanning
    disk and clobbering the fake.
    """
    from omicsclaw.core.registry import SKILLS_DIR, registry

    monkeypatch.setattr(registry, "skills", skills, raising=False)
    monkeypatch.setattr(
        registry, "domains", domains if domains is not None else {"demo": {"name": "Demo"}},
        raising=False,
    )
    monkeypatch.setattr(registry, "_loaded", True, raising=False)
    monkeypatch.setattr(registry, "_loaded_dir", SKILLS_DIR.resolve(), raising=False)


def test_skill_runner_module_exposes_run_skill_contract():
    module = importlib.import_module("omicsclaw.core.skill_runner")

    assert hasattr(module, "run_skill")
    signature = inspect.signature(module.run_skill)
    assert list(signature.parameters) == [
        "skill_name",
        "input_path",
        "input_paths",
        "output_dir",
        "demo",
        "session_path",
        "extra_args",
        "stdout_callback",
        "stderr_callback",
        "cancel_event",
    ]


def test_root_omicsclaw_reexports_shared_run_skill():
    root = importlib.import_module("omicsclaw")
    runner = importlib.import_module("omicsclaw.core.skill_runner")

    assert root.run_skill is runner.run_skill


def test_run_skill_streams_stdout_and_stderr_lines_via_callbacks(tmp_path, monkeypatch):
    """The runner must surface skill output line-by-line in real time so that
    long-running deep-learning skills produce visible logs to the bot/operator
    instead of staying silent until completion."""
    skill_runner = importlib.import_module("omicsclaw.core.skill_runner")

    fake_script = tmp_path / "fake_streamer.py"
    fake_script.write_text(textwrap.dedent("""\
        import argparse, json, sys, time
        from pathlib import Path

        ap = argparse.ArgumentParser()
        ap.add_argument("--demo", action="store_true")
        ap.add_argument("--output", required=True)
        args = ap.parse_args()

        for i in range(3):
            print(f"epoch {i}/3", flush=True)
            time.sleep(0.02)
        print("warning: synthetic stderr", file=sys.stderr, flush=True)
        print("done", flush=True)

        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps({"summary": {"method": "fake"}}), encoding="utf-8")
    """), encoding="utf-8")

    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)
    _install_fake_skills(monkeypatch, {
        "fake-streamer": {
            "script": fake_script,
            "domain": "demo",
            "demo_args": ["--demo"],
            "allowed_extra_flags": set(),
            "description": "Streaming test skill",
        }
    })

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    result = skill_runner.run_skill(
        "fake-streamer",
        demo=True,
        output_dir=str(tmp_path / "out"),
        stdout_callback=stdout_lines.append,
        stderr_callback=stderr_lines.append,
    )

    assert result["success"] is True, result.get("stderr")
    assert stdout_lines == ["epoch 0/3", "epoch 1/3", "epoch 2/3", "done"]
    assert stderr_lines == ["warning: synthetic stderr"]
    # Aggregated stdout/stderr fields must still contain the same content.
    for line in stdout_lines:
        assert line in result["stdout"]
    assert "warning: synthetic stderr" in result["stderr"]


def test_run_skill_callback_exception_does_not_break_run(tmp_path, monkeypatch):
    """A buggy stdout/stderr callback must not abort the skill — the runner
    swallows callback errors so the underlying analysis still completes."""
    skill_runner = importlib.import_module("omicsclaw.core.skill_runner")

    fake_script = tmp_path / "fake_one_line.py"
    fake_script.write_text(textwrap.dedent("""\
        import argparse, json
        from pathlib import Path

        ap = argparse.ArgumentParser()
        ap.add_argument("--demo", action="store_true")
        ap.add_argument("--output", required=True)
        args = ap.parse_args()

        print("hello")
        Path(args.output).mkdir(parents=True, exist_ok=True)
        (Path(args.output) / "result.json").write_text(json.dumps({"summary": {}}), encoding="utf-8")
    """), encoding="utf-8")

    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)
    _install_fake_skills(monkeypatch, {
        "fake-one-line": {
            "script": fake_script,
            "domain": "demo",
            "demo_args": ["--demo"],
            "allowed_extra_flags": set(),
            "description": "One-line test skill",
        }
    })

    def boom(_line: str) -> None:
        raise RuntimeError("callback exploded")

    result = skill_runner.run_skill(
        "fake-one-line",
        demo=True,
        output_dir=str(tmp_path / "out"),
        stdout_callback=boom,
    )
    assert result["success"] is True
    assert "hello" in result["stdout"]


def test_run_skill_cancel_event_kills_long_running_subprocess(tmp_path, monkeypatch):
    """Setting ``cancel_event`` while a skill is running must terminate the
    child subprocess (and its process group) and return promptly.

    Pre-fix the runner's ``popen.wait()`` would not wake up for asyncio
    cancellation, so jobs cancelled by the FastAPI router would leak
    children that kept consuming CPU/GPU until they finished naturally.
    """
    skill_runner = importlib.import_module("omicsclaw.core.skill_runner")

    fake_script = tmp_path / "fake_long.py"
    fake_script.write_text(textwrap.dedent("""\
        import argparse, time
        ap = argparse.ArgumentParser()
        ap.add_argument("--demo", action="store_true")
        ap.add_argument("--output", required=True)
        args = ap.parse_args()
        for i in range(60):
            print(f"working {i}", flush=True)
            time.sleep(0.5)
    """), encoding="utf-8")

    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)
    _install_fake_skills(monkeypatch, {
        "fake-long": {
            "script": fake_script,
            "domain": "demo",
            "demo_args": ["--demo"],
            "allowed_extra_flags": set(),
            "description": "Long-running test skill",
        }
    })

    cancel_event = threading.Event()

    def _trigger_cancel_after_startup() -> None:
        # Wait for the child to actually start producing output before cancelling
        # so we exercise the real "kill while busy" path, not "kill before start".
        time.sleep(1.0)
        cancel_event.set()

    threading.Thread(target=_trigger_cancel_after_startup, daemon=True).start()

    started_at = time.time()
    result = skill_runner.run_skill(
        "fake-long",
        demo=True,
        output_dir=str(tmp_path / "long_out"),
        cancel_event=cancel_event,
    )
    elapsed = time.time() - started_at

    # Without cancellation the fake script would run for ~30s. Cancellation
    # must interrupt within a few seconds (1s pre-cancel + grace + cleanup).
    assert elapsed < 10, f"cancel did not interrupt; ran for {elapsed:.1f}s"
    assert result["success"] is False
    assert result["exit_code"] != 0


def test_run_skill_cancellation_with_partial_result_json_is_not_reported_as_success(
    tmp_path, monkeypatch
):
    """A skill that wrote ``result.json`` early then was SIGKILL'd via
    ``cancel_event`` must NOT be silently reclassified as success.

    Pre-fix, the runner mapped any ``returncode == -9`` to ``0`` whenever
    ``result.json`` existed (originally a workaround for the orphan reaper's
    SIGKILL race). After we wired ``cancel_event`` through SIGTERM/SIGKILL,
    ``-9`` also became the *normal* outcome of cancellation — so cancelled
    runs that happened to leave a partial ``result.json`` were silently
    reported as ``success=True``.
    """
    skill_runner = importlib.import_module("omicsclaw.core.skill_runner")

    fake_script = tmp_path / "fake_partial_then_sleep.py"
    fake_script.write_text(textwrap.dedent("""\
        import argparse, json, signal, time
        from pathlib import Path
        # Ignore SIGTERM so the runner has to escalate to SIGKILL (-9), which is
        # exactly the path that used to trip the "-9 + result.json → success"
        # heuristic.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        ap = argparse.ArgumentParser()
        ap.add_argument("--demo", action="store_true")
        ap.add_argument("--output", required=True)
        args = ap.parse_args()
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(
            json.dumps({"summary": {"method": "fake", "partial": True}}),
            encoding="utf-8",
        )
        print("partial-result-written", flush=True)
        for _ in range(60):
            time.sleep(0.5)
    """), encoding="utf-8")

    monkeypatch.setattr(skill_runner, "DEFAULT_OUTPUT_ROOT", tmp_path)
    _install_fake_skills(monkeypatch, {
        "fake-partial": {
            "script": fake_script,
            "domain": "demo",
            "demo_args": ["--demo"],
            "allowed_extra_flags": set(),
            "description": "Partial-then-sleep test skill",
        }
    })

    cancel_event = threading.Event()

    def _trigger_cancel_after_partial_write() -> None:
        # Give the child time to write result.json before cancelling.
        time.sleep(1.0)
        cancel_event.set()

    threading.Thread(target=_trigger_cancel_after_partial_write, daemon=True).start()

    result = skill_runner.run_skill(
        "fake-partial",
        demo=True,
        output_dir=str(tmp_path / "partial_out"),
        cancel_event=cancel_event,
    )

    # The partial result.json was on disk when SIGKILL fired, which used to
    # trip the -9 → 0 heuristic. Cancellation must override the heuristic.
    assert result["success"] is False, (
        "cancelled run with partial result.json must NOT be reported as success"
    )
    assert result["exit_code"] != 0
