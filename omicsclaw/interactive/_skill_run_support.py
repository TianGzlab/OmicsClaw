"""Shared parsing and presentation helpers for `/run` skill execution."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

from ._history_support import (
    build_skill_run_history_messages,
    build_skill_run_result_text,
)


@dataclass(slots=True)
class SkillRunCommandArgs:
    skill: str
    demo: bool = False
    input_path: str | None = None
    output_dir: str | None = None
    method: str | None = None

    @property
    def extra_args(self) -> list[str]:
        args: list[str] = []
        if self.method:
            args.extend(["--method", self.method])
        return args


@dataclass(slots=True)
class SkillRunDisplayView:
    skill: str
    success: bool
    duration_seconds: float = 0.0
    output_dir: str = ""
    method: str = ""
    readme_path: str = ""
    notebook_path: str = ""
    stdout: str = ""
    error: str = ""
    exception: bool = False


@dataclass(slots=True)
class SkillRunExecutionView:
    skill: str
    success: bool
    result_text: str
    history_messages: list[dict[str, str]] = field(default_factory=list)
    system_summary_lines: list[str] = field(default_factory=list)
    stdout: str = ""

    @property
    def system_message(self) -> str:
        return "\n".join(self.system_summary_lines)


def parse_skill_run_command(arg: str) -> SkillRunCommandArgs | None:
    raw = arg.strip()
    if not raw:
        return None

    try:
        tokens = shlex.split(raw)
    except ValueError:
        return None
    if not tokens:
        return None

    input_path = None
    output_dir = None
    method = None
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--input="):
            input_path = token.split("=", 1)[1]
            i += 1
        elif token.startswith("--output="):
            output_dir = token.split("=", 1)[1]
            i += 1
        elif token.startswith("--method="):
            method = token.split("=", 1)[1]
            i += 1
        elif token == "--input":
            if i + 1 >= len(tokens):
                return None
            input_path = tokens[i + 1]
            i += 2
        elif token == "--output":
            if i + 1 >= len(tokens):
                return None
            output_dir = tokens[i + 1]
            i += 2
        elif token == "--method":
            if i + 1 >= len(tokens):
                return None
            method = tokens[i + 1]
            i += 2
        else:
            i += 1

    return SkillRunCommandArgs(
        skill=tokens[0],
        demo="--demo" in tokens,
        input_path=input_path,
        output_dir=output_dir,
        method=method,
    )


def build_skill_run_display_view(
    skill: str,
    result: dict[str, Any],
) -> SkillRunDisplayView:
    return SkillRunDisplayView(
        skill=skill,
        success=bool(result.get("success")),
        duration_seconds=float(result.get("duration_seconds", 0) or 0),
        output_dir=str(result.get("output_dir", "") or ""),
        method=str(result.get("method", "") or ""),
        readme_path=str(result.get("readme_path", "") or ""),
        notebook_path=str(result.get("notebook_path", "") or ""),
        stdout=str(result.get("stdout", "") or ""),
        error=str(result.get("stderr", "unknown error") or "unknown error"),
        exception=bool(result.get("exception")),
    )


def format_skill_run_system_summary(
    view: SkillRunDisplayView,
) -> list[str]:
    if view.success:
        lines = [
            f"✓ Skill '{view.skill}' completed in {view.duration_seconds:.1f}s",
            f"  Output: {view.output_dir or '?'}",
        ]
        if view.method:
            lines.append(f"  Method: {view.method}")
        if view.readme_path:
            lines.append(f"  Guide: {view.readme_path}")
        if view.notebook_path:
            lines.append(f"  Notebook: {view.notebook_path}")
        return lines

    if view.exception:
        return [f"⚠ Error running skill '{view.skill}': {view.error[:300]}"]

    return [f"✗ Skill '{view.skill}' failed: {view.error[:300]}"]


def build_skill_run_execution_view(
    command: str,
    *,
    skill: str,
    result: dict[str, Any],
) -> SkillRunExecutionView:
    display = build_skill_run_display_view(skill, result)
    return SkillRunExecutionView(
        skill=skill,
        success=display.success,
        result_text=build_skill_run_result_text(skill, result),
        history_messages=build_skill_run_history_messages(
            command,
            skill=skill,
            result=result,
        ),
        system_summary_lines=format_skill_run_system_summary(display),
        stdout=display.stdout,
    )


def build_skill_run_exception_result(error: Exception) -> dict[str, Any]:
    return {
        "success": False,
        "stderr": str(error),
        "output_dir": "",
        "exception": True,
    }
