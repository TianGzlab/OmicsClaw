"""Default job executor wiring.

The default local app/remote executor calls the shared
``omicsclaw.core.skill_runner.arun_skill`` contract — the async-native
sibling of ``run_skill`` introduced in OMI-12 audit P1 #4. The previous
``await asyncio.to_thread(run_skill)`` wrapping was the culprit behind
ThreadPoolExecutor exhaustion under multi-user load (one parked worker
per long-running skill); the async path spawns via
``asyncio.create_subprocess_exec`` instead so concurrent skills only
cost one event-loop task each.

The legacy ``default_command_factory`` remains available for external
process executors such as SSH/Slurm wrappers that still need CLI argv.

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

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from omicsclaw.autoagent.constants import param_to_cli_flag
from omicsclaw.core.skill_result import SkillRunResult, result_json_fallback

from .base import JobContext, JobOutcome


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
    """Executor that invokes the shared in-process skill runner.

    Runs via ``omicsclaw.core.skill_runner.arun_skill`` (async-native) so
    concurrent jobs cost one event-loop task each, not one parked
    ``ThreadPoolExecutor`` worker per long-running skill — see OMI-12
    audit P1 #4 for the original thread-pool-exhaustion regression.
    """

    async def run(self, ctx: JobContext) -> JobOutcome:
        # Late import so callers / tests that monkeypatch
        # ``omicsclaw.core.skill_runner.arun_skill`` see the patched
        # function at call time, the same way the previous
        # ``run_skill`` monkeypatching worked.
        from omicsclaw.core import skill_runner

        input_path = ctx.inputs.get("input") or ctx.inputs.get("path")
        input_paths = ctx.inputs.get("inputs")
        demo = bool(ctx.inputs.get("demo"))
        extra_args = _params_to_extra_args(ctx.params)

        try:
            run_result = await skill_runner.arun_skill(
                ctx.skill,
                input_path=str(input_path) if input_path else None,
                input_paths=[str(item) for item in input_paths] if input_paths else None,
                output_dir=str(ctx.artifact_root),
                demo=demo,
                session_path=str(ctx.inputs["session_path"]) if ctx.inputs.get("session_path") else None,
                extra_args=extra_args or None,
            )
        except asyncio.CancelledError:
            # ``adrive_subprocess`` already SIGTERM/SIGKILL'd the process
            # group before re-raising; just propagate so the jobs router
            # records the cancelled-terminal state.
            raise
        except Exception as exc:
            text = f"skill_runner_failed: {exc}"
            ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
            ctx.stdout_log.write_text(text, encoding="utf-8")
            return JobOutcome(exit_code=1, error=text, stdout_text=text)

        stdout_text = run_result.combined_output
        if not stdout_text:
            stdout_text = result_json_fallback(run_result)

        ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
        ctx.stdout_log.write_text(stdout_text, encoding="utf-8")

        exit_code = run_result.adapter_exit_code
        error = None if exit_code == 0 else run_result.stderr or stdout_text or "skill_runner_failed"
        return JobOutcome(exit_code=exit_code, error=error, stdout_text=stdout_text)


def build_default_executor() -> SkillRunnerExecutor:
    return SkillRunnerExecutor()
