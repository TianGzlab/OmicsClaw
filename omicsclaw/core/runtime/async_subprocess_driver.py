"""Async sibling of :mod:`subprocess_driver` for the executor path.

OMI-12 audit P1 #4: ``SkillRunnerExecutor`` used to wrap the blocking
``run_skill`` call in ``asyncio.to_thread``, which parked one
ThreadPoolExecutor worker per active skill. With the default 32-worker
pool, a busy app-server running long skills (velocity, pseudotime, …)
could exhaust the pool and stall unrelated async work.

This module replaces that thread-blocking path with a native
``asyncio.create_subprocess_exec`` driver that exposes the same outcome
shape as the sync ``drive_subprocess`` (a :class:`subprocess.CompletedProcess`
with the status-field-aware return code logic from P1 #2). The sync
driver stays in place for the CLI / bot / pipeline-runner paths that
already run inside their own threads or processes; this driver is the
async-native counterpart for callers that already live in an asyncio
event loop.

Behaviour parity with the sync driver:

- ``start_new_session=True`` so cancellation can SIGTERM/SIGKILL the
  whole process group, not just the leader.
- Cancel path: ``asyncio.CancelledError`` raised on the awaiting task
  flows into SIGTERM → wait ``_CANCEL_GRACE_SECONDS`` → SIGKILL → re-raise.
- Status field / ``-9 → 0`` heuristic from :func:`read_result_status`
  applies identically.

Behaviour deltas vs the sync driver (small + documented):

- Cancellation comes from ``asyncio.CancelledError`` rather than a
  ``threading.Event`` poll loop. asyncio cancellation is decisive; we
  never reclassify a cancelled run as success regardless of any partial
  ``status: ok`` left on disk.
- Per-line ``stdout_callback`` / ``stderr_callback`` are not supported
  here — the executor sink writes the aggregated output to
  ``ctx.stdout_log`` after the process exits. The bot path that needs
  per-line streaming continues to use the sync ``run_skill`` directly.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from pathlib import Path

from omicsclaw.common.report import read_result_status


_CANCEL_GRACE_SECONDS = 5.0


async def _read_stream(stream: asyncio.StreamReader | None) -> bytes:
    if stream is None:
        return b""
    return await stream.read()


async def _terminate_process_group(proc: asyncio.subprocess.Process) -> None:
    """SIGTERM the child's process group, wait for the grace period, then SIGKILL.

    Mirrors the sync driver's cancel watcher. ``start_new_session=True``
    at spawn time means the child is its own process-group leader, so
    ``os.killpg`` reaches every grandchild — important for skills that
    fork workers (multiprocessing, joblib, …).
    """
    if proc.returncode is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError, OSError):
        return

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return

    try:
        await asyncio.wait_for(proc.wait(), timeout=_CANCEL_GRACE_SECONDS)
    except asyncio.TimeoutError:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            await proc.wait()
        except Exception:
            pass


async def adrive_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    out_dir: Path,
) -> subprocess.CompletedProcess:
    """Spawn ``cmd`` via ``asyncio.create_subprocess_exec``, return a
    ``CompletedProcess`` with the same status-field / SIGKILL-heuristic
    semantics as the sync :func:`drive_subprocess`.

    Raises :class:`asyncio.CancelledError` when the awaiting task is
    cancelled; the child's process group is SIGTERM'd (then SIGKILL'd
    after the grace period) before the exception propagates.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
        env=env,
        start_new_session=True,
    )

    cancelled = False
    try:
        stdout_bytes, stderr_bytes = await asyncio.gather(
            _read_stream(proc.stdout),
            _read_stream(proc.stderr),
        )
        await proc.wait()
    except asyncio.CancelledError:
        cancelled = True
        await _terminate_process_group(proc)
        raise
    finally:
        if not cancelled and proc.returncode is None:
            # Defensive: any other exit path should still reap the child
            # so a half-spawned process doesn't outlive the executor.
            await _terminate_process_group(proc)

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return_code = proc.returncode if proc.returncode is not None else -1

    # Status field + ``-9 → 0`` fallback — same semantics as the sync
    # driver. Cancellation never gets here (we re-raised above).
    status = read_result_status(out_dir)
    if status == "ok":
        return_code = 0
    elif status in ("partial", "failed"):
        if return_code == 0:
            return_code = 1
    elif return_code == -9 and (out_dir / "result.json").exists():
        return_code = 0

    return subprocess.CompletedProcess(cmd, return_code, stdout, stderr)
