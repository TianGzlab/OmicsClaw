"""Build the subprocess argv for ``run_skill`` and filter forwarded flags.

Two responsibilities live here:

1. ``build_skill_argv`` — assemble the full ``[PYTHON, script, --input ...,
   --output ...]`` argv from the resolved skill entry. Demo mode, multi-input
   mode, single-input mode, and the "no inputs at all" error are mutually
   exclusive; the helper returns ``None`` on the error path so the caller
   can surface a stable error result.

2. ``filter_forwarded_args`` — keep only the LLM-supplied extra flags that
   the skill's SKILL.md frontmatter explicitly allow-lists, rewrite the
   common ``--epochs`` / ``--n-epochs`` alias mismatch in one place, and
   never let the caller smuggle ``--input``, ``--output``, or ``--demo``
   past the runner's own resolution.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable


_BLOCKED_FLAGS = frozenset({"--input", "--output", "--demo"})


def extract_flag_value(tokens: list[str] | None, flag: str) -> str | None:
    """Return the value associated with ``flag`` in an argv-style token list.

    Handles both ``--flag value`` and ``--flag=value`` forms; whitespace is
    stripped. ``None`` is returned when the flag is absent or trailing.
    """
    if not tokens:
        return None
    for idx, token in enumerate(tokens):
        if token == flag and idx + 1 < len(tokens):
            return str(tokens[idx + 1]).strip()
        if token.startswith(f"{flag}="):
            return token.split("=", 1)[1].strip()
    return None


def build_user_run_command(
    *,
    skill_name: str,
    demo: bool,
    input_path: str | None,
    output_dir: Path,
    forwarded_args: list[str] | None = None,
) -> list[str]:
    """Build a user-facing ``oc run`` command for provenance and notebooks."""
    cmd = ["oc", "run", skill_name]
    if demo:
        cmd.append("--demo")
    elif input_path:
        cmd.extend(["--input", input_path])
    cmd.extend(["--output", str(output_dir)])
    if forwarded_args:
        cmd.extend(forwarded_args)
    return cmd


def build_skill_argv(
    *,
    python_executable: str,
    script_path: Path,
    skill_info: dict[str, Any],
    demo: bool,
    input_path: str | None,
    input_paths: Iterable[str] | None,
    output_dir: Path,
) -> list[str] | None:
    """Build the ``[python, script.py, --input ..., --output ...]`` argv.

    Returns ``None`` when no input source is provided (no ``--input``,
    no ``--demo``, no multi-input list). The caller is expected to convert
    that into a stable ``_err`` result.
    """
    cmd: list[str] = [python_executable, str(script_path)]
    if demo:
        cmd.extend(skill_info.get("demo_args", ["--demo"]))
    elif input_paths:
        for path in input_paths:
            cmd.extend(["--input", str(path)])
    elif input_path:
        cmd.extend(["--input", str(input_path)])
    else:
        return None

    cmd.extend(["--output", str(output_dir)])
    return cmd


def _is_numeric_literal(token: str) -> bool:
    return bool(re.fullmatch(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", token))


def _next_token_is_value(tokens: list[str], idx: int) -> bool:
    if idx + 1 >= len(tokens):
        return False
    nxt = tokens[idx + 1]
    if not nxt.startswith("-"):
        return True
    return _is_numeric_literal(nxt)


def filter_forwarded_args(
    extra_args: list[str] | None,
    *,
    allowed_extra_flags: Iterable[str] | None,
) -> list[str]:
    """Drop anything not on the skill's allow-list; rewrite epoch aliases.

    The runner accepts LLM-supplied extra flags only when the skill's
    SKILL.md frontmatter explicitly allow-lists them. ``--input``,
    ``--output``, and ``--demo`` are always blocked since the runner
    resolves those itself.
    """
    if not extra_args:
        return []

    allowed: set[str] = set(allowed_extra_flags or ())
    filtered: list[str] = []
    i = 0
    while i < len(extra_args):
        token = extra_args[i]
        flag = token.split("=")[0]
        has_inline_value = "=" in token

        # Tolerate the common ``--epochs`` ↔ ``--n-epochs`` alias mismatch in
        # one place so callers don't have to special-case every skill.
        if flag == "--n-epochs" and "--n-epochs" not in allowed and "--epochs" in allowed:
            token = token.replace("--n-epochs", "--epochs", 1)
            flag = "--epochs"
        elif flag == "--epochs" and "--epochs" not in allowed and "--n-epochs" in allowed:
            token = token.replace("--epochs", "--n-epochs", 1)
            flag = "--n-epochs"

        if flag in _BLOCKED_FLAGS:
            i += 2 if (not has_inline_value and _next_token_is_value(extra_args, i)) else 1
            continue
        if flag in allowed:
            filtered.append(token)
            if not has_inline_value and _next_token_is_value(extra_args, i):
                filtered.append(extra_args[i + 1])
                i += 1
        i += 1
    return filtered
