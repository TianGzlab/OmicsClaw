from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tool_executor import ToolCallable, build_executor_map
from .tool_spec import ToolSpec


@dataclass(frozen=True, slots=True)
class ToolRuntime:
    specs: tuple[ToolSpec, ...]
    specs_by_name: dict[str, ToolSpec]
    openai_tools: tuple[dict[str, Any], ...]
    executors: dict[str, ToolCallable]


class ToolRegistry:
    """Ordered registry for tool specs shared across entry surfaces."""

    def __init__(self, specs: list[ToolSpec] | tuple[ToolSpec, ...]):
        names: set[str] = set()
        ordered: list[ToolSpec] = []
        for spec in specs:
            if spec.name in names:
                raise ValueError(f"Duplicate tool name: {spec.name}")
            names.add(spec.name)
            ordered.append(spec)
        self._specs = tuple(ordered)

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return self._specs

    def for_surface(self, surface: str) -> "ToolRegistry":
        return ToolRegistry([spec for spec in self._specs if surface in spec.surfaces])

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [spec.to_openai_tool() for spec in self._specs]

    def build_runtime(self, available_executors: dict[str, ToolCallable]) -> ToolRuntime:
        return ToolRuntime(
            specs=self._specs,
            specs_by_name={spec.name: spec for spec in self._specs},
            openai_tools=tuple(self.to_openai_tools()),
            executors=build_executor_map(self._specs, available_executors),
        )
