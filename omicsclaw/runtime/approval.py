from __future__ import annotations

from .policy_state import ToolPolicyState
from .tool_spec import (
    APPROVAL_MODE_ASK,
    APPROVAL_MODE_AUTO,
    APPROVAL_MODE_DENY_UNLESS_TRUSTED,
    ToolSpec,
)


def is_tool_approval_satisfied(
    tool_name: str,
    spec: ToolSpec,
    state: ToolPolicyState,
) -> bool:
    mode = str(spec.approval_mode or APPROVAL_MODE_AUTO).strip() or APPROVAL_MODE_AUTO

    if mode == APPROVAL_MODE_AUTO:
        return True
    if mode == APPROVAL_MODE_ASK:
        return state.auto_approve_ask or tool_name in state.approved_tool_names
    if mode == APPROVAL_MODE_DENY_UNLESS_TRUSTED:
        return state.trusted
    return False


__all__ = ["is_tool_approval_satisfied"]
