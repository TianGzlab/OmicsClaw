from __future__ import annotations

import importlib
import inspect
import json
import sys
import textwrap
from pathlib import Path


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
    monkeypatch.setattr(skill_runner, "SKILLS", {
        "fake-streamer": {
            "script": fake_script,
            "domain": "demo",
            "demo_args": ["--demo"],
            "allowed_extra_flags": set(),
            "description": "Streaming test skill",
        }
    })
    monkeypatch.setattr(skill_runner, "DOMAINS", {"demo": {"name": "Demo"}})

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
    monkeypatch.setattr(skill_runner, "SKILLS", {
        "fake-one-line": {
            "script": fake_script,
            "domain": "demo",
            "demo_args": ["--demo"],
            "allowed_extra_flags": set(),
            "description": "One-line test skill",
        }
    })
    monkeypatch.setattr(skill_runner, "DOMAINS", {"demo": {"name": "Demo"}})

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
