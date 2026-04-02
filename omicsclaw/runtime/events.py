from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

EVENT_SESSION_START = "session_start"
EVENT_SESSION_RESUME = "session_resume"
EVENT_PLAN_CREATED = "plan_created"
EVENT_PLAN_APPROVED = "plan_approved"
EVENT_TASK_STARTED = "task_started"
EVENT_TASK_COMPLETED = "task_completed"
EVENT_TOOL_BEFORE = "tool_before"
EVENT_TOOL_AFTER = "tool_after"
EVENT_VERIFICATION_COMPLETED = "verification_completed"
EVENT_EXTENSION_INSTALLED = "extension_installed"

VALID_LIFECYCLE_EVENTS = frozenset(
    {
        EVENT_SESSION_START,
        EVENT_SESSION_RESUME,
        EVENT_PLAN_CREATED,
        EVENT_PLAN_APPROVED,
        EVENT_TASK_STARTED,
        EVENT_TASK_COMPLETED,
        EVENT_TOOL_BEFORE,
        EVENT_TOOL_AFTER,
        EVENT_VERIFICATION_COMPLETED,
        EVENT_EXTENSION_INSTALLED,
    }
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    name: str
    payload: dict[str, Any]
    surface: str = ""
    session_id: str = ""
    chat_id: str = ""
    workspace: str = ""
    source: str = ""
    timestamp: str = field(default_factory=_utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "payload": dict(self.payload),
            "surface": self.surface,
            "session_id": self.session_id,
            "chat_id": self.chat_id,
            "workspace": self.workspace,
            "source": self.source,
            "timestamp": self.timestamp,
        }


__all__ = [
    "EVENT_EXTENSION_INSTALLED",
    "EVENT_PLAN_APPROVED",
    "EVENT_PLAN_CREATED",
    "EVENT_SESSION_RESUME",
    "EVENT_SESSION_START",
    "EVENT_TASK_COMPLETED",
    "EVENT_TASK_STARTED",
    "EVENT_TOOL_AFTER",
    "EVENT_TOOL_BEFORE",
    "EVENT_VERIFICATION_COMPLETED",
    "LifecycleEvent",
    "VALID_LIFECYCLE_EVENTS",
]
