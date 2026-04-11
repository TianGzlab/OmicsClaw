"""Helpers for reusing the upstream OmicsClaw live notebook session.

The research pipeline keeps a single module-level `_nb_session` instance in
`omicsclaw.agents.tools`. When the app backend opens that exact notebook path,
it should bind to the already-running kernel instead of spawning a parallel
kernel process.

This module also patches the upstream `NotebookSession` class at runtime to
attach a shared lock and lightweight status bookkeeping. That gives the app
backend and the pipeline one serialization point around the kernel client so
they do not steal each other's iopub/shell messages.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_STATE_ATTR = "__omicsclaw_app_live_state__"
_PATCHED_ATTR = "__omicsclaw_app_live_patch__"
_patch_lock = threading.Lock()


@dataclass
class LiveNotebookState:
    """Shared per-session coordination state installed onto NotebookSession."""

    lock: threading.RLock = field(default_factory=threading.RLock)
    status: str = "idle"
    last_activity: float = field(default_factory=time.time)
    generation: int = 0

    def touch(self) -> None:
        self.last_activity = time.time()


@dataclass
class LiveSessionBinding:
    """Resolved live pipeline notebook session for a concrete notebook path."""

    session: Any
    state: LiveNotebookState
    file_path: str

    @property
    def cwd(self) -> str:
        return str(Path(self.file_path).parent)


def install_live_session_support() -> None:
    """Patch the upstream NotebookSession class once per process."""
    with _patch_lock:
        try:
            from omicsclaw.agents.notebook_session import NotebookSession
        except Exception:
            return

        if getattr(NotebookSession, _PATCHED_ATTR, False):
            return

        orig_init = NotebookSession.__init__
        orig_execute_source = NotebookSession._execute_source
        orig_restart_kernel = NotebookSession.restart_kernel
        orig_shutdown = NotebookSession.shutdown

        def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
            orig_init(self, *args, **kwargs)
            state = _ensure_state(self)
            state.status = _status_from_session(self)
            state.touch()

        def patched_execute_source(
            self: Any,
            source: str,
            *,
            timeout: int | None = None,
        ) -> dict[str, Any]:
            state = _ensure_state(self)
            with state.lock:
                state.status = "busy"
                state.touch()
                try:
                    return orig_execute_source(self, source, timeout=timeout)
                finally:
                    state.status = _status_from_session(self)
                    state.touch()

        def patched_restart_kernel(self: Any) -> dict[str, Any]:
            state = _ensure_state(self)
            with state.lock:
                state.generation += 1
                state.status = "starting"
                state.touch()
                try:
                    result = orig_restart_kernel(self)
                except Exception:
                    state.status = _status_from_session(self)
                    state.touch()
                    raise
                state.status = _status_from_session(self)
                state.touch()
                return result

        def patched_shutdown(self: Any) -> None:
            state = _ensure_state(self)
            with state.lock:
                state.generation += 1
                try:
                    orig_shutdown(self)
                finally:
                    state.status = "dead"
                    state.touch()

        NotebookSession.__init__ = patched_init
        NotebookSession._execute_source = patched_execute_source
        NotebookSession.restart_kernel = patched_restart_kernel
        NotebookSession.shutdown = patched_shutdown
        setattr(NotebookSession, _PATCHED_ATTR, True)


def resolve_live_session(file_path: Optional[str]) -> Optional[LiveSessionBinding]:
    """Return the active upstream `_nb_session` when it matches `file_path`."""
    if not file_path:
        return None

    install_live_session_support()

    try:
        from omicsclaw.agents.tools import _nb_session  # type: ignore
    except Exception:
        return None

    if _nb_session is None:
        return None

    try:
        requested = str(Path(file_path).resolve())
        live_path = str(Path(_nb_session.path).resolve())
    except Exception:
        return None

    if requested != live_path:
        return None

    state = _ensure_state(_nb_session)
    state.status = _status_from_session(_nb_session, preferred=state.status)
    state.touch()
    return LiveSessionBinding(
        session=_nb_session,
        state=state,
        file_path=live_path,
    )


def is_live_session_running(binding: LiveSessionBinding) -> bool:
    return _status_from_session(binding.session, preferred=binding.state.status) != "dead"


def ensure_live_state(session: Any) -> LiveNotebookState:
    return _ensure_state(session)


def _ensure_state(session: Any) -> LiveNotebookState:
    state = getattr(session, _STATE_ATTR, None)
    if isinstance(state, LiveNotebookState):
        return state
    state = LiveNotebookState()
    state.status = _status_from_session(session)
    setattr(session, _STATE_ATTR, state)
    return state


def _status_from_session(session: Any, *, preferred: str | None = None) -> str:
    try:
        alive = bool(session.km.is_alive())
    except Exception:
        alive = False
    if not alive:
        return "dead"
    if preferred == "busy":
        return "busy"
    return "idle"
