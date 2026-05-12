"""Phase 1 (T1.3) RED tests for ``ToolSpec.predicate`` + ``select_tool_specs``.

Mirrors the Phase 4 ``ContextLayerInjector.predicate`` design so the
runtime tool-list assembly can drop tools that don't apply to the
current request. Same fail-closed semantics: a misbehaving predicate
suppresses the tool (and logs WARNING) rather than crashing assembly.

Six invariants pinned:
1. ToolSpec without predicate is always selected.
2. ToolSpec with predicate=True is selected.
3. ToolSpec with predicate=False is filtered out.
4. Predicate exception → fail-closed (filtered + WARNING).
5. ``select_tool_specs`` preserves original order.
6. ``ToolRegistry.to_openai_tools_for_request`` returns the filtered
   payload that the LLM would actually receive.
"""

from __future__ import annotations

import logging

import pytest

from omicsclaw.runtime.context_layers import ContextAssemblyRequest
from omicsclaw.runtime.tool_registry import ToolRegistry, select_tool_specs
from omicsclaw.runtime.tool_spec import ToolSpec


def _spec(name: str, predicate=None) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"{name} description",
        parameters={"type": "object", "properties": {}},
        surfaces=("bot",),
        predicate=predicate,
    )


def _req(**kwargs) -> ContextAssemblyRequest:
    return ContextAssemblyRequest(**kwargs)


def test_tool_spec_without_predicate_is_always_selected() -> None:
    spec = _spec("always_on")
    selected = select_tool_specs((spec,), request=_req(surface="bot"))
    assert [s.name for s in selected] == ["always_on"]


def test_tool_spec_with_predicate_returning_true_is_selected() -> None:
    spec = _spec("active", predicate=lambda req: True)
    selected = select_tool_specs((spec,), request=_req(surface="bot"))
    assert [s.name for s in selected] == ["active"]


def test_tool_spec_with_predicate_returning_false_is_filtered_out() -> None:
    spec = _spec("inactive", predicate=lambda req: False)
    selected = select_tool_specs((spec,), request=_req(surface="bot"))
    assert selected == ()


def test_predicate_raising_exception_is_fail_closed_and_logged(caplog) -> None:
    def bad_predicate(_req: ContextAssemblyRequest) -> bool:
        raise ValueError("synthetic predicate failure")

    spec = _spec("bad", predicate=bad_predicate)
    with caplog.at_level(logging.WARNING):
        selected = select_tool_specs((spec,), request=_req(surface="bot"))
    assert selected == (), "fail-closed: tool must be suppressed on predicate exception"
    joined = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "bad" in joined
    assert "synthetic predicate failure" in joined or "predicate" in joined.lower()


def test_select_tool_specs_preserves_original_order() -> None:
    a = _spec("a")
    b = _spec("b", predicate=lambda req: True)
    c = _spec("c")
    d = _spec("d", predicate=lambda req: False)
    e = _spec("e")
    selected = select_tool_specs((a, b, c, d, e), request=_req(surface="bot"))
    assert [s.name for s in selected] == ["a", "b", "c", "e"]


def test_tool_registry_to_openai_tools_for_request_returns_filtered_payload() -> None:
    a = _spec("a")
    b = _spec("b", predicate=lambda req: bool(req.workspace))
    c = _spec("c", predicate=lambda req: False)
    registry = ToolRegistry([a, b, c])

    no_workspace = registry.to_openai_tools_for_request(_req(surface="bot"))
    with_workspace = registry.to_openai_tools_for_request(
        _req(surface="bot", workspace="/tmp/x")
    )

    assert [tool["function"]["name"] for tool in no_workspace] == ["a"]
    assert [tool["function"]["name"] for tool in with_workspace] == ["a", "b"]
    # Backward-compatible: ``to_openai_tools()`` (no request) still returns all.
    assert [tool["function"]["name"] for tool in registry.to_openai_tools()] == [
        "a",
        "b",
        "c",
    ]


def test_select_tool_specs_honors_surface_gating() -> None:
    """Surface match remains a prerequisite — predicate runs only after."""
    a = ToolSpec(
        name="bot_only",
        description="d",
        parameters={"type": "object"},
        surfaces=("bot",),
    )
    b = ToolSpec(
        name="cli_only",
        description="d",
        parameters={"type": "object"},
        surfaces=("interactive",),
    )
    selected = select_tool_specs((a, b), request=_req(surface="bot"))
    assert [s.name for s in selected] == ["bot_only"]


def test_predicate_emits_predicate_hit_event_via_existing_sink() -> None:
    """Reuse the Phase 1 ``register_predicate_event_sink`` so tool-list
    selection telemetry flows through the same channel as context-layer
    predicates. Closes the Phase 4 review's "sink unused" leftover."""
    from omicsclaw.runtime.context_layers import (
        register_predicate_event_sink,
        unregister_predicate_event_sink,
    )
    from omicsclaw.runtime import events

    captured = []
    sink_id = register_predicate_event_sink(captured.append)
    try:
        spec = _spec("probe", predicate=lambda req: True)
        select_tool_specs((spec,), request=_req(surface="bot"))
    finally:
        unregister_predicate_event_sink(sink_id)

    names = [evt.name for evt in captured]
    assert events.EVENT_PREDICATE_HIT in names, (
        f"expected EVENT_PREDICATE_HIT to be emitted via the shared sink; "
        f"saw {names}"
    )
    # Payload should at least name the tool whose predicate fired.
    assert any(evt.payload.get("predicate") == "probe" for evt in captured)


def test_predicate_event_distinguishes_tool_from_layer_source() -> None:
    """Tool-selection events must be tagged ``source='tool_registry.predicate'``
    + ``kind='tool'`` so consumers can disambiguate from context-layer
    predicate events that share the sink (avoids ambiguous events when a
    layer and a tool happen to share a predicate name)."""
    from omicsclaw.runtime.context_layers import (
        register_predicate_event_sink,
        unregister_predicate_event_sink,
    )

    captured = []
    sink_id = register_predicate_event_sink(captured.append)
    try:
        spec = _spec("probe", predicate=lambda req: True)
        select_tool_specs((spec,), request=_req(surface="bot"))
    finally:
        unregister_predicate_event_sink(sink_id)

    assert captured, "no events captured"
    evt = captured[0]
    assert evt.source == "tool_registry.predicate", (
        f"tool-selection events must distinguish source; got {evt.source!r}"
    )
    assert evt.payload.get("kind") == "tool", (
        f"tool-selection events must carry kind='tool'; got "
        f"{evt.payload.get('kind')!r}"
    )
