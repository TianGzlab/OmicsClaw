"""Default job executor wiring.

The default local app/remote executor calls the shared
``omicsclaw.core.skill_runner.run_skill`` contract directly. The legacy
``default_command_factory`` remains available for external process executors
such as SSH/Slurm wrappers that still need CLI argv.

Mapping from wire contract (``JobContext.inputs`` + ``JobContext.params``)
to runner kwargs or CLI argv:

- ``inputs["demo"] == True``   → ``--demo``
- ``inputs["input"] | "path"`` → ``--input <value>`` (first non-empty wins)
- ``params["<key>"] == True``  → ``--<kebab-key>`` (standalone flag)
- ``params["<key>"] == False`` → omitted (NOT ``--no-...``)
- ``params["<key>"] is None``  → omitted
- other ``params["<key>"]``     → ``--<kebab-key> <str(value)>``

The factory is a pure ``JobContext -> list[str]`` function so it can be
unit-tested without spawning, and so future executors (Slurm, SSH) can
reuse the same argv shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from omicsclaw.autoagent.constants import param_to_cli_flag

import asyncio

from .base import JobContext, JobOutcome
from .subprocess import SubprocessExecutor


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENTRY_POINT = _PROJECT_ROOT / "omicsclaw.py"


def _coerce_param_value(value: Any) -> str:
    if isinstance(value, (str, int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def default_command_factory(ctx: JobContext) -> list[str]:
    argv: list[str] = [
        sys.executable,
        str(_ENTRY_POINT),
        "run",
        ctx.skill,
        "--output",
        str(ctx.artifact_root),
    ]

    if ctx.inputs.get("demo"):
        argv.append("--demo")

    input_path = ctx.inputs.get("input") or ctx.inputs.get("path")
    if input_path:
        argv.extend(["--input", str(input_path)])

    for key, value in ctx.params.items():
        if value is None or value is False:
            continue
        flag = param_to_cli_flag(key)
        if value is True:
            argv.append(flag)
        else:
            argv.extend([flag, _coerce_param_value(value)])

    return argv


def _params_to_extra_args(params: dict[str, Any]) -> list[str]:
    extra_args: list[str] = []
    for key, value in params.items():
        if value is None or value is False:
            continue
        flag = param_to_cli_flag(key)
        if value is True:
            extra_args.append(flag)
        else:
            extra_args.extend([flag, _coerce_param_value(value)])
    return extra_args


class SkillRunnerExecutor:
    """Executor that invokes the shared in-process skill runner."""

    async def run(self, ctx: JobContext) -> JobOutcome:
        from omicsclaw.core import skill_runner

        input_path = ctx.inputs.get("input") or ctx.inputs.get("path")
        input_paths = ctx.inputs.get("inputs")
        demo = bool(ctx.inputs.get("demo"))
        extra_args = _params_to_extra_args(ctx.params)

        def _run() -> dict[str, Any]:
            return skill_runner.run_skill(
                ctx.skill,
                input_path=str(input_path) if input_path else None,
                input_paths=[str(item) for item in input_paths] if input_paths else None,
                output_dir=str(ctx.artifact_root),
                demo=demo,
                session_path=str(ctx.inputs["session_path"]) if ctx.inputs.get("session_path") else None,
                extra_args=extra_args or None,
            )

        try:
            result = await asyncio.to_thread(_run)
        except Exception as exc:
            text = f"skill_runner_failed: {exc}"
            ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
            ctx.stdout_log.write_text(text, encoding="utf-8")
            return JobOutcome(exit_code=1, error=text, stdout_text=text)

        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        stdout_text = stdout + (stderr if not stdout or not stderr else "\n" + stderr)
        if not stdout_text:
            stdout_text = json.dumps(result, ensure_ascii=False, default=str)

        ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
        ctx.stdout_log.write_text(stdout_text, encoding="utf-8")

        exit_code = int(result.get("exit_code") or 0)
        if not result.get("success", False) and exit_code == 0:
            exit_code = 1
        error = None if exit_code == 0 else stderr or stdout_text or "skill_runner_failed"
        return JobOutcome(exit_code=exit_code, error=error, stdout_text=stdout_text)


def build_default_executor() -> SkillRunnerExecutor:
    return SkillRunnerExecutor()
