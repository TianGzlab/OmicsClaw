from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _coerce_names(raw_value: Any) -> frozenset[str]:
    if raw_value is None:
        return frozenset()
    if isinstance(raw_value, str):
        raw_items = [raw_value]
    elif isinstance(raw_value, (list, tuple, set, frozenset)):
        raw_items = list(raw_value)
    else:
        raw_items = [raw_value]

    values = [str(item).strip() for item in raw_items if str(item).strip()]
    return frozenset(values)


@dataclass(frozen=True, slots=True)
class ToolPolicyState:
    surface: str = ""
    trusted: bool = False
    background: bool = False
    auto_approve_ask: bool = False
    approved_tool_names: frozenset[str] = frozenset()

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any] | "ToolPolicyState" | None,
        *,
        surface: str = "",
    ) -> "ToolPolicyState":
        if isinstance(raw, cls):
            resolved_surface = raw.surface or surface
            if resolved_surface == raw.surface:
                return raw
            return cls(
                surface=resolved_surface,
                trusted=raw.trusted,
                background=raw.background,
                auto_approve_ask=raw.auto_approve_ask,
                approved_tool_names=raw.approved_tool_names,
            )

        if not raw:
            return cls(surface=surface)

        return cls(
            surface=str(raw.get("surface") or surface or "").strip(),
            trusted=bool(raw.get("trusted", False)),
            background=bool(raw.get("background", False)),
            auto_approve_ask=bool(raw.get("auto_approve_ask", False)),
            approved_tool_names=_coerce_names(raw.get("approved_tool_names")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "trusted": self.trusted,
            "background": self.background,
            "auto_approve_ask": self.auto_approve_ask,
            "approved_tool_names": sorted(self.approved_tool_names),
        }


__all__ = ["ToolPolicyState"]
