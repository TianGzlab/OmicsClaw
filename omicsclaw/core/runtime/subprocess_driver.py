"""Spawn a skill subprocess, stream its output, and honour cancellation.

This is the only place that touches ``subprocess.Popen`` for the runner.
It owns three daemon threads:

- ``_reaper``: waits for the main process to exit, then SIGKILLs the
  whole process group so an orphaned child cannot keep consuming
  CPU / GPU.
- ``_cancel_watcher``: when ``cancel_event`` fires, SIGTERMs the
  process group, waits ``_CANCEL_GRACE_SECONDS``, then SIGKILLs anything
  still alive.
- One thread per stream that pumps stdout / stderr line-by-line to
  optional callbacks so long-running skills produce visible logs in
  real time instead of going silent until completion.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable


_CANCEL_GRACE_SECONDS = 5.0
_THREAD_JOIN_TIMEOUT_SECONDS = 5.0


def _stream_to_sink(
    stream,
    sink: list[str],
    callback: Callable[[str], None] | None,
) -> None:
    """Drain ``stream`` line-by-line into ``sink`` and forward to ``callback``.

    ``callback`` receives each line stripped of its trailing newline. Callback
    exceptions are swallowed so a buggy log handler cannot abort the run.
    """
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            sink.append(line)
            if callback is not None:
                try:
                    callback(line.rstrip("\n"))
                except Exception:
                    # The skill must complete even if the consumer's logger blows up.
                    pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def drive_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    out_dir: Path,
    stdout_callback: Callable[[str], None] | None = None,
    stderr_callback: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> subprocess.CompletedProcess:
    """Run ``cmd`` as a subprocess, return a ``CompletedProcess``.

    ``out_dir`` is consulted by the ``-9 → 0`` heuristic only: when the main
    process is SIGKILL'd but had already produced a ``result.json``, we treat
    it as success — unless the kill was caused by ``cancel_event`` firing,
    in which case the cancellation must remain visible to the caller.
    """
    popen = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered so callbacks fire as the skill prints
        cwd=str(cwd),
        env=env,
        start_new_session=True,
    )

    def _reaper() -> None:
        """Wait for main process exit, then kill orphaned siblings."""
        popen.wait()
        time.sleep(0.5)
        try:
            os.killpg(os.getpgid(popen.pid), 9)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def _cancel_watcher() -> None:
        """Send SIGTERM (then SIGKILL after grace) when cancel_event is set."""
        if cancel_event is None:
            return
        while popen.poll() is None:
            if cancel_event.wait(timeout=0.2):
                try:
                    os.killpg(os.getpgid(popen.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    return
                grace_deadline = time.time() + _CANCEL_GRACE_SECONDS
                while popen.poll() is None and time.time() < grace_deadline:
                    time.sleep(0.1)
                if popen.poll() is None:
                    try:
                        os.killpg(os.getpgid(popen.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass
                return

    reap_thread = threading.Thread(target=_reaper, daemon=True)
    reap_thread.start()
    cancel_thread: threading.Thread | None = None
    if cancel_event is not None:
        cancel_thread = threading.Thread(target=_cancel_watcher, daemon=True)
        cancel_thread.start()

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    stdout_thread = threading.Thread(
        target=_stream_to_sink,
        args=(popen.stdout, stdout_lines, stdout_callback),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_stream_to_sink,
        args=(popen.stderr, stderr_lines, stderr_callback),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    try:
        popen.wait()
    except Exception:
        pass
    stdout_thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
    stderr_thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
    reap_thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
    if cancel_thread is not None:
        cancel_thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)

    stdout = "".join(stdout_lines)
    stderr = "".join(stderr_lines)
    return_code = popen.returncode or 0

    # The ``-9 → 0`` heuristic was a workaround for the orphan reaper's
    # SIGKILL race when the main process had already produced its
    # ``result.json``. Once ``cancel_event`` was wired to escalate to
    # SIGKILL, ``-9`` also became the *normal* outcome of cancellation —
    # skip the heuristic when the run was actually cancelled, otherwise a
    # cancelled run that happened to leave a partial ``result.json`` would
    # be silently reported as success.
    was_cancelled = cancel_event is not None and cancel_event.is_set()
    if (
        not was_cancelled
        and return_code == -9
        and (out_dir / "result.json").exists()
    ):
        return_code = 0

    return subprocess.CompletedProcess(cmd, return_code, stdout, stderr)
