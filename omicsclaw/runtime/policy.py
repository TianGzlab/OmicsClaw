from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .approval import is_tool_approval_satisfied
from .policy_state import ToolPolicyState
from .tool_spec import (
    APPROVAL_MODE_ASK,
    APPROVAL_MODE_AUTO,
    APPROVAL_MODE_DENY_UNLESS_TRUSTED,
    RISK_LEVEL_LOW,
    ToolSpec,
)

TOOL_POLICY_ALLOW = "allow"
TOOL_POLICY_REQUIRE_APPROVAL = "require_approval"
TOOL_POLICY_DENY = "deny"


def _policy_surface(
    runtime_context: Mapping[str, Any] | None,
    fallback_surface: str = "",
) -> str:
    if not runtime_context:
        return fallback_surface
    return str(runtime_context.get("surface") or fallback_surface or "").strip()


def build_tool_policy_state(
    runtime_context: Mapping[str, Any] | None,
    *,
    fallback_surface: str = "",
) -> ToolPolicyState:
    if not runtime_context:
        return ToolPolicyState(surface=fallback_surface)

    surface = _policy_surface(runtime_context, fallback_surface)
    state = ToolPolicyState.from_mapping(runtime_context.get("policy_state"), surface=surface)

    approved_tool_names = state.approved_tool_names
    raw_approved = runtime_context.get("approved_tool_names")
    if raw_approved:
        approved_tool_names = approved_tool_names.union(
            ToolPolicyState.from_mapping(
                {"approved_tool_names": raw_approved}
            ).approved_tool_names
        )

    return ToolPolicyState(
        surface=state.surface or surface,
        trusted=bool(runtime_context.get("trusted", state.trusted)),
        background=bool(runtime_context.get("background", state.background)),
        auto_approve_ask=bool(
            runtime_context.get("auto_approve_ask", state.auto_approve_ask)
        ),
        approved_tool_names=approved_tool_names,
    )


def _describe_capabilities(spec: ToolSpec) -> str:
    parts: list[str] = []

    if spec.writes_config:
        parts.append("modifies local configuration")
    elif spec.writes_workspace:
        parts.append("writes workspace files")

    if spec.touches_network:
        parts.append("uses network access")

    if not parts:
        if spec.read_only:
            parts.append("is read-only")
        else:
            parts.append("changes local state")

    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _hint_for_action(action: str) -> str:
    if action == TOOL_POLICY_REQUIRE_APPROVAL:
        return "Ask the user to confirm this action, then retry the request."
    if action == TOOL_POLICY_DENY:
        return "Run this tool only from a trusted context or choose a safer alternative."
    return ""


@dataclass(frozen=True, slots=True)
class ToolPolicyDecision:
    action: str
    reason: str
    risk_level: str
    approval_mode: str
    writes_workspace: bool
    writes_config: bool
    touches_network: bool
    allowed_in_background: bool
    policy_tags: tuple[str, ...]
    surface: str = ""
    background: bool = False
    trusted: bool = False
    hint: str = ""

    @property
    def allows_execution(self) -> bool:
        return self.action == TOOL_POLICY_ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "approval_mode": self.approval_mode,
            "writes_workspace": self.writes_workspace,
            "writes_config": self.writes_config,
            "touches_network": self.touches_network,
            "allowed_in_background": self.allowed_in_background,
            "policy_tags": list(self.policy_tags),
            "surface": self.surface,
            "background": self.background,
            "trusted": self.trusted,
            "hint": self.hint,
        }


def evaluate_tool_policy(
    tool_name: str,
    spec: ToolSpec | None,
    *,
    runtime_context: Mapping[str, Any] | None = None,
) -> ToolPolicyDecision | None:
    if spec is None:
        return None

    state = build_tool_policy_state(runtime_context)
    approval_mode = str(spec.approval_mode or APPROVAL_MODE_AUTO).strip() or APPROVAL_MODE_AUTO
    capability_text = _describe_capabilities(spec)
    action = TOOL_POLICY_ALLOW
    reason = f"`{tool_name}` is allowed because it {capability_text}."

    if state.background and not spec.allowed_in_background:
        action = TOOL_POLICY_DENY
        reason = (
            f"`{tool_name}` is blocked in background execution because it {capability_text} "
            "and is restricted to foreground use."
        )
    elif approval_mode == APPROVAL_MODE_DENY_UNLESS_TRUSTED and not state.trusted:
        action = TOOL_POLICY_DENY
        reason = (
            f"`{tool_name}` is blocked because it {capability_text} and only trusted "
            "runtime contexts may execute it."
        )
    elif approval_mode == APPROVAL_MODE_ASK and not is_tool_approval_satisfied(tool_name, spec, state):
        action = TOOL_POLICY_REQUIRE_APPROVAL
        reason = (
            f"`{tool_name}` requires explicit approval because it {capability_text}."
        )
    elif approval_mode == APPROVAL_MODE_ASK:
        reason = (
            f"`{tool_name}` is allowed because explicit approval was already satisfied "
            f"for an action that {capability_text}."
        )
    elif approval_mode == APPROVAL_MODE_DENY_UNLESS_TRUSTED:
        reason = (
            f"`{tool_name}` is allowed because the runtime is trusted for an action that "
            f"{capability_text}."
        )
    elif str(spec.risk_level or "").strip() == RISK_LEVEL_LOW and spec.read_only:
        reason = f"`{tool_name}` is allowed as a low-risk read-only operation."

    return ToolPolicyDecision(
        action=action,
        reason=reason,
        risk_level=str(spec.risk_level or RISK_LEVEL_LOW).strip() or RISK_LEVEL_LOW,
        approval_mode=approval_mode,
        writes_workspace=spec.writes_workspace,
        writes_config=spec.writes_config,
        touches_network=spec.touches_network,
        allowed_in_background=spec.allowed_in_background,
        policy_tags=tuple(spec.policy_tags),
        surface=state.surface,
        background=state.background,
        trusted=state.trusted,
        hint=_hint_for_action(action),
    )


def format_policy_block_message(
    tool_name: str,
    decision: ToolPolicyDecision,
) -> str:
    lines = [
        "[tool policy blocked]",
        f"tool: {tool_name}",
        f"action: {decision.action}",
        f"reason: {decision.reason}",
        f"risk: {decision.risk_level}",
        f"approval_mode: {decision.approval_mode}",
        f"writes_workspace: {str(decision.writes_workspace).lower()}",
        f"writes_config: {str(decision.writes_config).lower()}",
        f"touches_network: {str(decision.touches_network).lower()}",
        f"background: {str(decision.background).lower()}",
        f"trusted: {str(decision.trusted).lower()}",
    ]
    if decision.surface:
        lines.append(f"surface: {decision.surface}")
    if decision.policy_tags:
        lines.append(f"tags: {', '.join(decision.policy_tags)}")
    if decision.hint:
        lines.append(f"hint: {decision.hint}")
    return "\n".join(lines)


__all__ = [
    "TOOL_POLICY_ALLOW",
    "TOOL_POLICY_DENY",
    "TOOL_POLICY_REQUIRE_APPROVAL",
    "ToolPolicyDecision",
    "build_tool_policy_state",
    "evaluate_tool_policy",
    "format_policy_block_message",
]
