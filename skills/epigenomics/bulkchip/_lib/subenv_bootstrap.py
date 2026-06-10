"""Relocate a bulk-ChIP skill into the ``omicsclaw_bulkchip`` conda sub-env.

The OmicsClaw runner launches every skill with the agent env's Python
(``sys.executable`` — see ``omicsclaw/core/skill_runner.py``). That agent
env is intentionally lightweight: it carries the framework but none of the
bioinformatics CLIs (samtools, MACS2, HOMER, ...) or analysis Python libs
(pandas, pydeseq2, ...) the bulk-ChIP skills need.

``ensure_bulkchip_env()`` is called at module-import time by each
``bulkchip-*.py`` script, BEFORE its heavy ``_lib`` imports. If the process
is not already inside ``omicsclaw_bulkchip``, it re-execs itself there.

Why NOT ``mamba run``: ``mamba run`` generates a temporary wrapper shell
script that uses ``exec -- ...``; the bash ``exec`` builtin rejects ``--``
as an option on some systems (``exec: --: invalid option``). Instead this
shim locates the sub-env's interpreter directly, manually prepends the
sub-env ``bin/`` to ``PATH`` (so the CLIs the skill subprocesses to are
found), and ``os.execv``s that interpreter. This mirrors the bulk-ATAC
suite's ``_lib/subenv_bootstrap.py``.

Why this module stays import-safe everywhere: it imports only stdlib, so
it loads cleanly in the lightweight agent env — unlike the other ``_lib``
modules, which import pandas/numpy at module scope and would fail there.
That is exactly why the relocation has to happen *here*, before those
heavy imports are reached.

Design notes:
  * ``os.execv`` replaces the process image (PID preserved), so the
    OmicsClaw runner's subprocess handle and process-group cancellation
    signalling stay valid across the relocation.
  * A sentinel env var guards against an infinite re-exec loop if the
    sub-env is misconfigured.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

SUBENV_NAME = "omicsclaw_bulkchip"
_REEXEC_SENTINEL = "OMICSCLAW_BULKCHIP_REEXEC"


def _conda_base() -> Path | None:
    """Return the conda base prefix, or None if it cannot be determined.

    Uses ``conda info --base`` (offline, fast, authoritative). Prefers the
    ``conda`` executable for this query — ``mamba`` is only a fallback.
    """
    conda = shutil.which("conda") or shutil.which("mamba")
    if conda is None:
        return None
    try:
        out = subprocess.run(
            [conda, "info", "--base"],
            capture_output=True, text=True, check=True, timeout=60,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None
    base = Path(out)
    return base if base.is_dir() else None


def ensure_bulkchip_env() -> None:
    """Re-exec the calling script inside ``omicsclaw_bulkchip`` if needed.

    No-op when already inside the sub-env (``CONDA_DEFAULT_ENV`` matches),
    when a relocation was already attempted (sentinel set), when conda
    cannot be located, or when the sub-env has not been built yet — in the
    last two cases the script proceeds in-place so its own prerequisite
    checks surface an actionable error.
    """
    # A relocation was already attempted in this process tree — never loop.
    if os.environ.get(_REEXEC_SENTINEL) == "1":
        return
    # Already running inside the target sub-env.
    if os.environ.get("CONDA_DEFAULT_ENV") == SUBENV_NAME:
        return
    base = _conda_base()
    if base is None:
        return
    subenv = base / "envs" / SUBENV_NAME
    subenv_python = subenv / "bin" / "python"
    if not subenv_python.is_file():
        # Sub-env not built yet — defer to the caller's prerequisite checks.
        return
    subenv_bin = subenv / "bin"

    # Manually "enter" the sub-env for the re-exec'd process:
    #   - PATH: so the bulk-ChIP CLIs (samtools, MACS2, ...) resolve;
    #   - CONDA_DEFAULT_ENV / CONDA_PREFIX: so this shim's own re-entry
    #     guard sees we are now inside omicsclaw_bulkchip.
    os.environ[_REEXEC_SENTINEL] = "1"
    os.environ["PATH"] = f"{subenv_bin}{os.pathsep}{os.environ.get('PATH', '')}"
    os.environ["CONDA_DEFAULT_ENV"] = SUBENV_NAME
    os.environ["CONDA_PREFIX"] = str(subenv)

    # sys.argv[0] is the bulkchip-*.py script as the runner invoked it.
    script = Path(sys.argv[0]).resolve()
    # os.execv replaces this process (PID unchanged); the runner's process
    # handle + process-group signalling remain valid across the relocation.
    os.execv(str(subenv_python), [str(subenv_python), str(script), *sys.argv[1:]])
