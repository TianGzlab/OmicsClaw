"""Stop the runner once the process that started it has gone.

The runner runs in the foreground only. An agent often starts it through a
shell, for example ``cd proj && python run.py run analysis/01_qc | tail``.
A tool timeout may kill only that shell, and a shell that put the runner in
the background may simply exit; either way the runner is adopted by another
process and would keep its kernel running and the module lock held.

``run.py`` reads its parent process and process group before anything
else. :func:`watch_parent` checks them once and then from a daemon thread
every second. The runner counts as abandoned when its parent is no longer
the one it started under, or when its process group had another leader
(the shell) and that leader has exited, unless the group is the
foreground job of a terminal. Then the runner kills the running
kernel, ends the current step's ledger with a failed ``run_end``, deletes
that step's notebook from an earlier run, and exits, which releases the
lock.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
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
    notebook: Path | None = None


class Activity:
    """What the runner is doing, shared by the main thread and the watchdog.

    Hold ``lock`` while appending ``run_start``, while writing a step's
    notebook, log and ``run_end``, and while changing ``current``. The
    watchdog takes it and never gives it back, so nothing the main thread
    writes for a step follows the watchdog's own ``run_end``.
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
        if current.notebook is not None:
            try:
                current.notebook.unlink(missing_ok=True)
            except OSError:
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
        _say(f"run.py: {reason}; stopped while no step was running")
    os._exit(EXIT_CODE)


def _leader_gone(group: int) -> bool:
    """Whether *group*'s leader, another process than this one, has exited."""
    if group <= 1 or group == os.getpid():
        return False
    try:
        os.kill(group, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:
        with open(f"/proc/{group}/stat", encoding="ascii", errors="replace") as handle:
            return handle.read().rsplit(")", 1)[-1].split()[0] == "Z"
    except (OSError, IndexError):
        return False


def _terminal_foreground() -> bool:
    """Whether this process group is the foreground job of the controlling terminal.

    An interactive shell gives each pipeline its own group, led by the
    pipeline's first command, so in ``echo x | python run.py ...`` the
    leader exits at once while the shell is still waiting for the runner.
    """
    try:
        tty = os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY)
    except OSError:
        return False
    try:
        return os.tcgetpgrp(tty) == os.getpgrp()
    except OSError:
        return False
    finally:
        os.close(tty)


def abandoned(parent: int, group: int) -> bool:
    """Whether the runner has lost the process that started it (see the module docstring)."""
    return os.getppid() != parent or (_leader_gone(group) and not _terminal_foreground())


def watch_parent(parent: int, group: int, *, interval: float = 1.0) -> threading.Thread:
    """Stop now if the runner is already abandoned, else start a daemon thread that stops it when it is.

    :param parent: ``os.getppid()`` read at the runner's entry point.
    :param group: ``os.getpgrp()`` read at the same time.
    """
    if abandoned(parent, group):
        stop(PARENT_EXITED)

    def poll() -> None:
        while True:
            time.sleep(interval)
            if abandoned(parent, group):
                stop(PARENT_EXITED)

    thread = threading.Thread(target=poll, name="omicsclaw-parent-watch", daemon=True)
    thread.start()
    return thread
