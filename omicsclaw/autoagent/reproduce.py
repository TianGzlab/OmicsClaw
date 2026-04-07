"""Helpers for building shell-safe optimization reproduction commands."""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from typing import Any


def build_reproduce_command(
    *,
    skill_name: str,
    method: str,
    params: dict[str, Any] | None = None,
    fixed_params: dict[str, Any] | None = None,
    input_path: str = "",
    demo: bool = False,
    python_executable: str = "python",
    script_name: str = "omicsclaw.py",
    input_placeholder: str = "<your_data.h5ad>",
) -> str:
    groups: list[list[str]] = [
        [python_executable, script_name, "run", str(skill_name)],
    ]

    if demo:
        groups.append(["--demo"])
    else:
        groups.append(["--input", str(input_path).strip() or input_placeholder])

    groups.append(["--method", str(method)])

    normalized_params = dict(params or {})
    for name, value in normalized_params.items():
        _append_option_group(groups, name, value)

    for name, value in (fixed_params or {}).items():
        if name in normalized_params:
            continue
        _append_option_group(groups, name, value)

    return " \\\n  ".join(
        " ".join(shlex.quote(token) for token in group)
        for group in groups
    )


def _append_option_group(
    groups: list[list[str]],
    name: str,
    value: Any,
) -> None:
    if value is None:
        return

    flag = "--" + name.replace("_", "-")
    if isinstance(value, bool):
        if value:
            groups.append([flag])
        return

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        rendered = [str(item) for item in value if item is not None]
        if rendered:
            groups.append([flag, *rendered])
        return

    groups.append([flag, str(value)])
