"""
runlog.py — one persistent run log per skill.

Each epigenomics skill writes a single ``<output_dir>/<skill>.log`` capturing
both the INFO logger narrative (orchestration + ``_lib`` progress) and the raw
subprocess stdout/stderr that the ``_run``/``_run_shell`` helpers would
otherwise discard on success.

Mechanism (no per-function plumbing):
  * ``attach_run_log`` adds ONE ``logging.FileHandler`` to the root logger (so
    every ``getLogger(__name__)`` narrative propagates in) AND to a dedicated
    ``omicsclaw.toollog`` logger that has ``propagate=False`` — so raw tool
    output lands in the file only, never echoed to the console.
  * ``log_tool_output`` is called by the skills' ``_run``/``_run_shell`` after
    each ``subprocess.run``; it emits via ``omicsclaw.toollog``. When no handler
    is attached (e.g. ``_lib`` used standalone) the record is silently dropped.

Call ``attach_run_log`` from the skill's ``main()`` — i.e. AFTER any subenv
re-exec (``ensure_*_env``) — so the handler survives the relocation.
"""

from __future__ import annotations

import logging
from pathlib import Path

TOOL_LOGGER = "omicsclaw.toollog"


def attach_run_log(output_dir, skill_name: str, skill_version: str | None = None) -> Path:
    """Attach the per-skill run-log FileHandler; return the log path.

    Idempotent: if a run-log handler is already on the root logger (e.g. main()
    called twice in one process), this is a no-op and returns the path.
    """
    output_dir = Path(output_dir)
    log_path = output_dir / f"{skill_name}.log"

    root = logging.getLogger()
    if any(getattr(h, "_omicsclaw_run_log", False) for h in root.handlers):
        return log_path

    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    fh._omicsclaw_run_log = True  # type: ignore[attr-defined]
    root.addHandler(fh)

    # Ensure the INFO narrative actually reaches the file even if the caller
    # never ran logging.basicConfig (root would default to WARNING and drop it).
    # Skills already set INFO; this only lowers an unset/higher root level.
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)

    # Raw tool output funnels through the same handler, file-only.
    tl = logging.getLogger(TOOL_LOGGER)
    tl.setLevel(logging.INFO)
    tl.propagate = False
    tl.addHandler(fh)

    version = f" v{skill_version}" if skill_version else ""
    logging.getLogger(skill_name).info("─── run started (%s%s) ───", skill_name, version)
    return log_path


def log_tool_output(cmd, result) -> None:
    """Append a command's stdout/stderr block to the run log (file only).

    ``cmd`` may be an argv list or a shell string; ``result`` is the
    ``subprocess.CompletedProcess``. Safe to call when no run-log handler is
    attached — the dedicated logger simply has no handlers and drops the record.
    """
    cmd_str = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
    logging.getLogger(TOOL_LOGGER).info(
        "$ %s\n[exit %s]\nSTDOUT:\n%s\nSTDERR:\n%s",
        cmd_str, getattr(result, "returncode", "?"),
        getattr(result, "stdout", ""), getattr(result, "stderr", ""),
    )
