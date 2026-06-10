"""Shared subprocess helpers for the bulk-Hi-C downstream ``_lib`` modules.

Identical-shape to the per-module ``_run``/``_run_shell``/``_require`` used by
``mapping.py`` and ``matrix.py``; factored out because the four downstream
cooltools wrappers (compartments / insulation / loops / pileup) all need them.
Every tool invocation routes through ``omicsclaw.common.runlog.log_tool_output``
so its stdout/stderr lands in the per-skill run log.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)


def check(tool: str) -> bool:
    """True if *tool* is on PATH (non-fatal)."""
    return shutil.which(tool) is not None


def require(tool: str) -> None:
    if not shutil.which(tool):
        raise RuntimeError(
            f"'{tool}' not found in PATH.\n"
            f"Install: conda install -c conda-forge -c bioconda {tool}"
        )


def run(cmd: list[str], *, label: str) -> subprocess.CompletedProcess:
    logger.info("Running: %s", label)
    result = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}")
    return result


def run_shell(cmd: str, *, label: str) -> subprocess.CompletedProcess:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}")
    return result
