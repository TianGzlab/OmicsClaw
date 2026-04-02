from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

RESULT_POLICY_INLINE = "inline"
RESULT_POLICY_SUMMARY_OR_MEDIA = "summary_or_media"
RESULT_POLICY_MEMORY_WRITE = "memory_write"
RESULT_POLICY_KNOWLEDGE_REFERENCE = "knowledge_reference"
RESULT_POLICY_INSPECTION_REFERENCE = "inspection_reference"
RESULT_POLICY_WEB_REFERENCE = "web_reference"

PROGRESS_POLICY_DEFAULT = "default"
PROGRESS_POLICY_ANALYSIS = "analysis"

RISK_LEVEL_LOW = "low"
RISK_LEVEL_MEDIUM = "medium"
RISK_LEVEL_HIGH = "high"

APPROVAL_MODE_AUTO = "auto"
APPROVAL_MODE_ASK = "ask"
APPROVAL_MODE_DENY_UNLESS_TRUSTED = "deny_unless_trusted"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Single-source definition for one tool's schema and runtime metadata."""

    name: str
    description: str
    parameters: dict[str, Any]
    executor_name: str | None = None
    surfaces: tuple[str, ...] = ("bot",)
    context_params: tuple[str, ...] = ()
    read_only: bool = False
    concurrency_safe: bool = False
    result_policy: str = RESULT_POLICY_INLINE
    progress_policy: str = PROGRESS_POLICY_DEFAULT
    risk_level: str = RISK_LEVEL_LOW
    approval_mode: str = APPROVAL_MODE_AUTO
    writes_workspace: bool = False
    writes_config: bool = False
    touches_network: bool = False
    allowed_in_background: bool = True
    policy_tags: tuple[str, ...] = ()

    @property
    def resolved_executor_name(self) -> str:
        return self.executor_name or self.name

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": deepcopy(self.parameters),
            },
        }


__all__ = [
    "APPROVAL_MODE_ASK",
    "APPROVAL_MODE_AUTO",
    "APPROVAL_MODE_DENY_UNLESS_TRUSTED",
    "PROGRESS_POLICY_ANALYSIS",
    "PROGRESS_POLICY_DEFAULT",
    "RESULT_POLICY_INLINE",
    "RESULT_POLICY_INSPECTION_REFERENCE",
    "RESULT_POLICY_KNOWLEDGE_REFERENCE",
    "RESULT_POLICY_MEMORY_WRITE",
    "RESULT_POLICY_SUMMARY_OR_MEDIA",
    "RESULT_POLICY_WEB_REFERENCE",
    "RISK_LEVEL_HIGH",
    "RISK_LEVEL_LOW",
    "RISK_LEVEL_MEDIUM",
    "ToolSpec",
]
