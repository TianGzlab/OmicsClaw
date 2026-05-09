from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .tool_executor import ToolCallable, build_executor_map
from .tool_spec import ToolSpec

_LOGGER = logging.getLogger("omicsclaw.runtime.tool_registry")


def select_tool_specs(
    specs: tuple[ToolSpec, ...] | list[ToolSpec],
    *,
    request: Any,
) -> tuple[ToolSpec, ...]:
    """Filter ``specs`` to those that should be visible for the given request.

    Filtering rules (in order):
      1. ``request.surface`` must be in ``spec.surfaces`` — surface gating
         remains a prerequisite.
      2. If ``spec.predicate is None``, the tool is included (always-on).
      3. Otherwise ``spec.predicate(request)`` is called under try/except.
         A raising predicate is fail-closed: the tool is suppressed and a
         WARNING is logged. A return value of False suppresses the tool.

    Order is preserved.

    On predicate evaluation, ``EVENT_PREDICATE_HIT`` /
    ``EVENT_PREDICATE_MISS`` events are emitted through the shared
    predicate-event sink registered via
    ``omicsclaw.runtime.context_layers.register_predicate_event_sink`` —
    this gives the Phase 4 predicate hook a production producer beyond
    context-layer telemetry.
    """
    surface = str(getattr(request, "surface", "") or "").strip()
    selected: list[ToolSpec] = []

    from .context_layers import _emit_predicate_event  # type: ignore[attr-defined]
    from . import events as _events_mod

    for spec in specs:
        if spec.surfaces and surface and surface not in spec.surfaces:
            continue
        if spec.predicate is None:
            selected.append(spec)
            continue
        try:
            decision = bool(spec.predicate(request))
        except Exception as exc:
            _LOGGER.warning(
                "Predicate for tool %r raised %s: %s; suppressing tool",
                spec.name,
                exc.__class__.__name__,
                exc,
            )
            continue
        try:
            _emit_predicate_event(
                _events_mod.EVENT_PREDICATE_HIT
                if decision
                else _events_mod.EVENT_PREDICATE_MISS,
                predicate=spec.name,
                surface=surface,
                source="tool_registry.predicate",
                kind="tool",
            )
        except Exception:  # pragma: no cover - never break selection on telemetry failure
            pass
        if decision:
            selected.append(spec)

    return tuple(selected)


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

    def to_openai_tools_for_request(self, request: Any) -> list[dict[str, Any]]:
        """Per-request filtered openai-tool payload.

        ``to_openai_tools()`` (no request) still returns the full list —
        callers that haven't migrated keep the legacy behavior.
        """
        return [
            spec.to_openai_tool()
            for spec in select_tool_specs(self._specs, request=request)
        ]

    def build_runtime(self, available_executors: dict[str, ToolCallable]) -> ToolRuntime:
        return ToolRuntime(
            specs=self._specs,
            specs_by_name={spec.name: spec for spec in self._specs},
            openai_tools=tuple(self.to_openai_tools()),
            executors=build_executor_map(self._specs, available_executors),
        )
