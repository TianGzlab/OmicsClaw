"""Skill execution helpers for chaining runs from a single tool call.

``run_skill_via_shared_runner`` is the core async wrapper around
``omicsclaw.core.skill_runner.run_skill`` — it composes forwarded
CLI args, streams stdout/stderr through callbacks, surfaces
user-guidance blocks extracted from skill output, and returns a
uniform result dict that callers (bot tool dispatch, auto-prepare
chain) can consume without duplicating wire-up.

``run_omics_skill_step`` is a higher-level convenience that builds a
fresh timestamped output directory under a caller-supplied
``output_root`` before delegating. ``normalize_extra_args`` filters
the user-supplied ``--`` arg list to drop ``--output`` (the runner
owns that) and rewrite snake_case flags to kebab-case.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path

from omicsclaw.common.report import build_output_dir_name
from omicsclaw.common.user_guidance import (
    extract_user_guidance_lines,
    render_guidance_block,
    strip_user_guidance_lines,
)
from omicsclaw.runtime.skill_lookup import lookup_skill_info

logger = logging.getLogger("omicsclaw.runtime.skill_chain")


def normalize_extra_args(extra_args) -> list[str]:
    if not extra_args or not isinstance(extra_args, list):
        return []
    filtered = []
    skip_next = False
    for arg in extra_args:
        if skip_next:
            skip_next = False
            continue
        if arg == "--output":
            skip_next = True
            continue
        if arg.startswith("--output="):
            continue
        if arg.startswith("--"):
            eq_pos = arg.find("=")
            if eq_pos > 0:
                flag_part = arg[:eq_pos].replace("_", "-")
                arg = flag_part + arg[eq_pos:]
            else:
                arg = arg.replace("_", "-")
        filtered.append(arg)
    return filtered


async def run_skill_via_shared_runner(
    *,
    skill_key: str,
    input_path: str | None,
    session_path: str | None,
    mode: str,
    method: str = "",
    data_type: str = "",
    batch_key: str = "",
    n_epochs: int | None = None,
    extra_args: list[str] | None = None,
    out_dir: Path,
) -> dict:
    from omicsclaw.core import skill_runner
    from omicsclaw.core.skill_result import SkillRunResult

    runner_skill = "spatial-pipeline" if skill_key == "pipeline" else skill_key
    skill_info = lookup_skill_info(runner_skill)
    canonical_skill = skill_info.get("alias") or runner_skill

    forwarded_args: list[str] = []
    if method:
        forwarded_args.extend(["--method", method])
    if data_type:
        forwarded_args.extend(["--data-type", data_type])
    if batch_key:
        forwarded_args.extend(["--batch-key", batch_key])
    if n_epochs is not None:
        # The legacy alias ``spatial-domain-identification`` was the only skill
        # that wanted ``--epochs`` instead of ``--n-epochs``, but the registry
        # now resolves that alias to canonical ``spatial-domains`` before we
        # land here — the conditional was dead code. ``argv_builder``'s
        # ``--epochs`` ↔ ``--n-epochs`` rewrite (see
        # ``omicsclaw/core/runtime/argv_builder.py``) handles whichever flag
        # each skill's ``allowed_extra_flags`` actually accepts.
        forwarded_args.extend(["--n-epochs", str(int(n_epochs))])
    forwarded_args.extend(normalize_extra_args(extra_args))

    def _emit_stdout(line: str) -> None:
        logger.info("[%s:stdout] %s", canonical_skill, line)

    def _emit_stderr(line: str) -> None:
        logger.info("[%s:stderr] %s", canonical_skill, line)

    cancel_event = threading.Event()

    def _run() -> SkillRunResult:
        return skill_runner.run_skill(
            runner_skill,
            input_path=str(input_path) if input_path else None,
            output_dir=str(out_dir),
            demo=mode == "demo",
            session_path=session_path,
            extra_args=forwarded_args or None,
            stdout_callback=_emit_stdout,
            stderr_callback=_emit_stderr,
            cancel_event=cancel_event,
        )

    try:
        run_result = await asyncio.to_thread(_run)
    except asyncio.CancelledError:
        cancel_event.set()
        raise
    stdout_str = run_result.stdout
    stderr_str = run_result.stderr
    guidance_block = render_guidance_block(extract_user_guidance_lines(stderr_str))
    clean_stderr = strip_user_guidance_lines(stderr_str)
    clean_stdout = strip_user_guidance_lines(stdout_str)
    error_text = clean_stderr[-1500:] if clean_stderr else clean_stdout[-1500:] if clean_stdout else "unknown error"
    returncode = run_result.adapter_exit_code
    output_dir = run_result.output_path or out_dir
    return {
        "success": run_result.success,
        "returncode": returncode,
        "out_dir": output_dir,
        "output_dir": str(output_dir),
        "stdout": stdout_str,
        "stderr": stderr_str,
        "guidance_block": guidance_block,
        "error_text": error_text,
    }


async def run_omics_skill_step(
    *,
    output_root: Path,
    skill_key: str,
    input_path: str | None,
    mode: str,
    method: str = "",
    data_type: str = "",
    batch_key: str = "",
    n_epochs: int | None = None,
    extra_args: list[str] | None = None,
) -> dict:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = output_root / build_output_dir_name(
        skill_key,
        ts,
        method=method,
        unique_suffix=uuid.uuid4().hex[:8],
    )

    return await run_skill_via_shared_runner(
        skill_key=skill_key,
        input_path=input_path,
        session_path=None,
        mode=mode,
        method=method,
        data_type=data_type,
        batch_key=batch_key,
        n_epochs=n_epochs,
        extra_args=extra_args,
        out_dir=out_dir,
    )


__all__ = [
    "normalize_extra_args",
    "run_skill_via_shared_runner",
    "run_omics_skill_step",
]
