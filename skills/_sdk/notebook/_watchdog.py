"""Stop the runner once the process that started it has gone.

An agent often starts the runner through a shell, for example
``cd proj && python run.py run analysis/01_qc | tail``. A tool timeout may
kill only that shell; the runner is then adopted by another process and
would keep its kernel running and the module lock held. :func:`watch_parent`
starts a daemon thread that polls ``os.getppid()``. When the parent changes,
the thread kills the running kernel, ends the current step's ledger with a
failed ``run_end`` and exits the process, which releases the lock.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PARENT_EXITED = "parent exited"
EXIT_CODE = 1


@dataclass
class Current:
    """The step being run now."""

    ledger: Any
    label: str
    started: float
    kill: Callable[[], None] | None


class Activity:
    """What the runner is doing, shared by the main thread and the watchdog.

    Hold ``lock`` while appending ``run_start`` or ``run_end`` and while
    changing ``current``; the watchdog takes it and never gives it back, so
    no other ``run_end`` follows its own.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.current: Current | None = None


ACTIVITY = Activity()


def _say(text: str) -> None:
    try:
        os.write(2, (text + "\n").encode("utf-8", "replace"))
    except OSError:
        pass


def stop(reason: str = PARENT_EXITED) -> None:
    """Kill the running kernel, end its step's ledger as failed, and exit the process."""
    ACTIVITY.lock.acquire()
    current = ACTIVITY.current
    if current is not None:
        if current.kill is not None:
            try:
                current.kill()
            except Exception:  # the process is about to exit either way
                pass
        try:
            current.ledger.append(
                "run_end",
                status="failed",
                seconds=round(time.perf_counter() - current.started, 3),
                error={"cell": None, "ename": "RunnerStopped", "evalue": reason},
                notebook=None,
                log=None,
                reason=reason,
            )
        except Exception:
            pass
        _say(f"run.py: {reason}; stopped {current.label}, killed its kernel and released the module lock")
    else:
        _say(f"run.py: {reason}; stopped and released the module lock")
    os._exit(EXIT_CODE)


def watch_parent(*, interval: float = 1.0) -> threading.Thread:
    """Start the daemon thread that calls :func:`stop` once ``os.getppid()`` changes."""
    parent = os.getppid()

    def poll() -> None:
        while True:
            time.sleep(interval)
            if os.getppid() != parent:
                stop(PARENT_EXITED)

    thread = threading.Thread(target=poll, name="omicsclaw-parent-watch", daemon=True)
    thread.start()
    return thread
