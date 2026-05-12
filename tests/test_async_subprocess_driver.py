"""Tests for ``omicsclaw.core.runtime.async_subprocess_driver`` (OMI-12 audit P1 #4).

The async driver replaces the ``asyncio.to_thread(run_skill)`` wrap that
``SkillRunnerExecutor`` used to do — pin the four corners of its
contract so a future "back to threads" change can't sneak in:

1. Happy-path captures stdout + stderr separately and returns exit_code=0.
2. ``-9 + result.json exists → 0`` legacy heuristic still fires (so
   skills that don't yet emit ``status: ok`` keep behaving the same).
3. ``status: ok`` overrides a non-zero exit code (the new P1 #2 contract
   carries over).
4. ``asyncio.CancelledError`` flows through and SIGTERMs the process
   group — even when the child ignores SIGTERM, the grace-period
   SIGKILL escalation closes the run promptly.
"""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
import time
from pathlib import Path

import pytest

from omicsclaw.core.runtime.async_subprocess_driver import adrive_subprocess


def _write_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_skill.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return script


def test_adrive_subprocess_captures_stdout_stderr_separately(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    script = _write_script(
        tmp_path,
        """
        import sys
        print("hello on stdout")
        print("warning on stderr", file=sys.stderr)
        """,
    )
    proc = asyncio.run(
        adrive_subprocess(
            [sys.executable, str(script)],
            cwd=tmp_path,
            env={},
            out_dir=out_dir,
        )
    )
    assert proc.returncode == 0
    assert "hello on stdout" in proc.stdout
    # stderr is captured separately — the executor merges them later when
    # writing ``ctx.stdout_log``.
    assert "warning on stderr" in proc.stderr


def test_adrive_subprocess_keeps_minus_9_to_zero_heuristic(tmp_path: Path):
    """When a skill exits via SIGKILL but already produced ``result.json``,
    the driver classifies it as success — preserving the legacy heuristic
    so the 89 skills that don't yet emit a status field don't regress."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    # The script writes result.json then SIGKILLs itself so the runner
    # observes exit code -9 with an existing envelope (no ``status``).
    script = _write_script(
        tmp_path,
        f"""
        import json, os, pathlib, signal
        out = pathlib.Path({str(out_dir)!r})
        (out / "result.json").write_text(json.dumps({{"skill": "stub"}}))
        os.kill(os.getpid(), signal.SIGKILL)
        """,
    )
    proc = asyncio.run(
        adrive_subprocess(
            [sys.executable, str(script)],
            cwd=tmp_path,
            env={},
            out_dir=out_dir,
        )
    )
    assert proc.returncode == 0, (
        f"SIGKILL with existing result.json must map to success; got {proc.returncode}"
    )


def test_adrive_subprocess_honours_status_ok_over_non_zero_exit(tmp_path: Path):
    """``status: ok`` short-circuits exit-code analysis — same semantics
    the sync driver already exposes (OMI-12 P1 #2 carrying over)."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    script = _write_script(
        tmp_path,
        f"""
        import json, pathlib, sys
        out = pathlib.Path({str(out_dir)!r})
        (out / "result.json").write_text(
            json.dumps({{"skill": "stub", "status": "ok"}})
        )
        sys.exit(7)  # arbitrary non-zero
        """,
    )
    proc = asyncio.run(
        adrive_subprocess(
            [sys.executable, str(script)],
            cwd=tmp_path,
            env={},
            out_dir=out_dir,
        )
    )
    assert proc.returncode == 0


def test_adrive_subprocess_terminates_process_group_on_cancel(tmp_path: Path):
    """``asyncio.CancelledError`` must propagate AND the child's process
    group must die — including children that ignore SIGTERM (the
    canonical "skill forked workers" case)."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Ignore SIGTERM so the driver has to escalate to the grace-period
    # SIGKILL. Without process-group kill semantics this script would
    # leak.
    script = _write_script(
        tmp_path,
        """
        import signal, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        # Sleep long enough that any successful cancel must be due to a
        # forcible kill, not the script exiting on its own.
        for _ in range(60):
            time.sleep(0.5)
        """,
    )

    async def driver() -> tuple[bool, float]:
        cancelled = False
        started = time.time()
        task = asyncio.create_task(
            adrive_subprocess(
                [sys.executable, str(script)],
                cwd=tmp_path,
                env={},
                out_dir=out_dir,
            )
        )
        await asyncio.sleep(0.4)  # let the child install its SIGTERM handler
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            cancelled = True
        return cancelled, time.time() - started

    cancelled, elapsed = asyncio.run(driver())
    assert cancelled, "adrive_subprocess must re-raise CancelledError"
    # ``_CANCEL_GRACE_SECONDS`` is 5.0 — the child should be dead within
    # roughly that grace + a bit of slack. Without SIGKILL escalation the
    # script would sleep for 30s.
    assert elapsed < 10.0, (
        f"cancel did not kill the child within the grace period — "
        f"elapsed {elapsed:.1f}s (expected < 10s)"
    )
