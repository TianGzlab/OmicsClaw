"""Typed session state for the interactive CLI loop.

Replaces the legacy ``state: dict[str, Any]`` pattern in
``omicsclaw/interactive/interactive.py`` with a documented dataclass whose
field set, defaults, and transitions are enforced rather than implied.

Keep this module free of imports from other ``interactive/`` submodules so
``_session_command_support`` and other helpers can adopt it without
introducing circular imports. Complex transitions that touch other
modules (e.g. refreshing ``session_metadata`` via ``build_session_metadata``)
live in those modules and take a ``SessionState`` as input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


_VALID_TIPS_LEVELS: frozenset[str] = frozenset({"verbose", "short", "off"})

_REQUIRED_KEYS: tuple[str, ...] = ("session_id", "workspace_dir", "ui_backend")
_LEGACY_DICT_KEYS: tuple[str, ...] = (
    "session_id",
    "workspace_dir",
    "ui_backend",
    "pipeline_workspace",
    "session_metadata",
    "messages",
    "running",
    "tips_enabled",
    "tips_level",
)


@dataclass
class SessionState:
    """Mutable per-session state for the interactive CLI loop.

    Required fields (must be supplied at construction):
      - ``session_id``: the persisted session identifier.
      - ``workspace_dir``: the active workspace path string.
      - ``ui_backend``: ``"cli"`` or ``"tui"``.

    Optional fields with documented defaults:
      - ``pipeline_workspace`` (``""``) — empty string means "no active pipeline".
      - ``session_metadata`` (``{}``) — derived view, refreshed via the helper
        in ``_session_command_support``.
      - ``messages`` (``[]``) — LLM message log, append-mostly.
      - ``running`` (``True``) — chat-loop sentinel; flipped by ``stop()``.
      - ``tips_enabled`` (``True``) — `/tips on|off` flag.
      - ``tips_level`` (``"verbose"``) — one of ``verbose|short|off``.
    """

    session_id: str
    workspace_dir: str
    ui_backend: str
    pipeline_workspace: str = ""
    session_metadata: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    running: bool = True
    tips_enabled: bool = True
    tips_level: str = "verbose"

    # ---- transitions -------------------------------------------------------

    def stop(self) -> None:
        """Flip the chat-loop sentinel so the next iteration exits."""
        self.running = False

    def set_tips(
        self,
        *,
        enabled: bool | None = None,
        level: str | None = None,
    ) -> None:
        """Update tips flag/level. ``None`` for either argument is a no-op so
        callers that forward optional CLI flags don't accidentally clear state.

        Raises ``ValueError`` if ``level`` is not in ``verbose|short|off``.
        """
        if enabled is not None:
            self.tips_enabled = bool(enabled)
        if level is not None:
            if level not in _VALID_TIPS_LEVELS:
                raise ValueError(
                    f"tips level must be one of {sorted(_VALID_TIPS_LEVELS)!r}, got {level!r}"
                )
            self.tips_level = level

    def set_pipeline_workspace(self, workspace: str | None) -> None:
        """Set the active pipeline workspace, normalizing ``None`` → ``""``.

        Note: refreshing ``session_metadata`` is intentionally NOT done here —
        that requires ``build_session_metadata`` from ``_session_command_support``
        and would create a circular import. Callers should use the helper in
        that module which takes a ``SessionState`` and updates both fields.
        """
        self.pipeline_workspace = workspace or ""

    # ---- migration adapters ------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        """Build from a legacy state dict. Raises if required keys are missing.

        Optional keys (``tips_enabled``, ``tips_level``, etc.) absorb the
        dataclass default if absent — matching the legacy ``state.get(k, …)``
        pattern.
        """
        for key in _REQUIRED_KEYS:
            if key not in data:
                raise KeyError(f"SessionState.from_dict missing required key: {key!r}")

        return cls(
            session_id=str(data["session_id"]),
            workspace_dir=str(data["workspace_dir"]),
            ui_backend=str(data["ui_backend"]),
            pipeline_workspace=str(data.get("pipeline_workspace", "") or ""),
            session_metadata=dict(data.get("session_metadata") or {}),
            messages=list(data.get("messages") or []),
            running=bool(data.get("running", True)),
            tips_enabled=bool(data.get("tips_enabled", True)),
            tips_level=str(data.get("tips_level") or "verbose"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Dump as the legacy state dict shape so partially-migrated callers
        keep working during the staged migration."""
        return {
            "session_id": self.session_id,
            "workspace_dir": self.workspace_dir,
            "ui_backend": self.ui_backend,
            "pipeline_workspace": self.pipeline_workspace,
            "session_metadata": self.session_metadata,
            "messages": self.messages,
            "running": self.running,
            "tips_enabled": self.tips_enabled,
            "tips_level": self.tips_level,
        }


__all__ = ["SessionState"]
