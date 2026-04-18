"""``JobContext`` → ``python omicsclaw.py run ...`` argv factory.

Mapping from wire contract (``JobContext.inputs`` + ``JobContext.params``)
to CLI argv:

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

from .base import JobContext
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


def build_default_executor() -> SubprocessExecutor:
    return SubprocessExecutor(command_factory=default_command_factory)
