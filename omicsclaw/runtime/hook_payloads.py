from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Mapping


def payload_to_dict(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, Mapping):
        return {str(key): value for key, value in payload.items()}
    if is_dataclass(payload):
        return asdict(payload)
    raise TypeError(f"Unsupported hook payload type: {type(payload)!r}")


@dataclass(frozen=True, slots=True)
class SessionHookPayload:
    chat_id: str
    session_id: str = ""
    surface: str = ""
    resumed: bool = False
    message_count: int = 0


@dataclass(frozen=True, slots=True)
class PlanHookPayload:
    request: str
    plan_kind: str
    status: str
    task_count: int
    workspace: str = ""
    session_id: str = ""
    source: str = ""


@dataclass(frozen=True, slots=True)
class TaskHookPayload:
    task_id: str
    title: str
    status: str
    owner: str = ""
    summary: str = ""
    workspace: str = ""
    plan_kind: str = ""
    source: str = ""
    artifact_refs: tuple[str, ...] = ()
    previous_status: str = ""


@dataclass(frozen=True, slots=True)
class ToolHookPayload:
    tool_name: str
    call_id: str = ""
    status: str = ""
    success: bool = False
    surface: str = ""
    session_id: str = ""
    chat_id: str = ""
    policy_action: str = ""


@dataclass(frozen=True, slots=True)
class VerificationHookPayload:
    workspace: str
    workspace_kind: str
    workspace_purpose: str
    status: str
    completed: bool
    missing_required_artifacts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    report_path: str = ""
    manifest_path: str = ""


@dataclass(frozen=True, slots=True)
class ExtensionHookPayload:
    extension_name: str
    extension_type: str
    source_kind: str
    install_path: str
    enabled: bool = True
    trusted_capabilities: tuple[str, ...] = ()
    manifest_version: str = ""


__all__ = [
    "ExtensionHookPayload",
    "PlanHookPayload",
    "SessionHookPayload",
    "TaskHookPayload",
    "ToolHookPayload",
    "VerificationHookPayload",
    "payload_to_dict",
]
