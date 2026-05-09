"""Phase 4 (Task 4.1) RED tests for the predicate-gated layer machinery.

The Phase 4 design adds an optional ``predicate`` field to
``ContextLayerInjector`` so a layer can opt into context-conditional
injection (e.g. "fire only when an absolute file path is in the user
query"). The tests pin four invariants:

1. A predicate that returns False suppresses the layer.
2. A predicate that returns True yields the layer (other gates being met).
3. A predicate that *raises* is fail-closed: the layer is suppressed and
   a warning is logged, so a buggy regex never breaks prompt assembly.
4. Predicate evaluation can emit ``EVENT_PREDICATE_HIT`` /
   ``EVENT_PREDICATE_MISS`` lifecycle events when an event sink is set.
"""

from __future__ import annotations

import logging

import pytest

from omicsclaw.runtime import events
from omicsclaw.runtime.context_layers import (
    ContextAssemblyRequest,
    ContextLayer,
    ContextLayerInjector,
)


def _builder(_request: ContextAssemblyRequest) -> ContextLayer:
    return ContextLayer(name="probe", content="hello", placement="system", order=99)


# --- True / False gating ------------------------------------------------------


def test_predicate_returning_true_yields_layer() -> None:
    inj = ContextLayerInjector(
        name="probe",
        order=99,
        placement="system",
        surfaces=("bot",),
        builder=_builder,
        predicate=lambda req: True,
    )
    assert inj.applies(ContextAssemblyRequest(surface="bot")) is True


def test_predicate_returning_false_suppresses_layer() -> None:
    inj = ContextLayerInjector(
        name="probe",
        order=99,
        placement="system",
        surfaces=("bot",),
        builder=_builder,
        predicate=lambda req: False,
    )
    assert inj.applies(ContextAssemblyRequest(surface="bot")) is False


def test_predicate_returning_false_overrides_matching_surface() -> None:
    """Surface match is necessary but not sufficient when a predicate exists."""
    inj = ContextLayerInjector(
        name="probe",
        order=99,
        placement="system",
        surfaces=("bot", "interactive", "pipeline"),
        builder=_builder,
        predicate=lambda req: req.workspace != "",
    )
    assert inj.applies(ContextAssemblyRequest(surface="bot")) is False
    assert inj.applies(ContextAssemblyRequest(surface="bot", workspace="/tmp/x")) is True


# --- Fail-closed semantics ---------------------------------------------------


def test_predicate_raising_exception_is_fail_closed_and_logged(caplog) -> None:
    def bad_predicate(_req: ContextAssemblyRequest) -> bool:
        raise ValueError("synthetic failure")

    inj = ContextLayerInjector(
        name="probe",
        order=99,
        placement="system",
        surfaces=("bot",),
        builder=_builder,
        predicate=bad_predicate,
    )
    with caplog.at_level(logging.WARNING):
        result = inj.applies(ContextAssemblyRequest(surface="bot"))
    assert result is False, "fail-closed: layer must NOT inject on predicate exception"
    # The warning message should name the injector and the underlying error.
    joined = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "probe" in joined
    assert "synthetic failure" in joined or "predicate" in joined.lower()


# --- Event emission ----------------------------------------------------------


def test_predicate_evaluation_emits_hit_and_miss_events() -> None:
    """When a predicate-evaluation event sink is registered, ``applies`` emits
    EVENT_PREDICATE_HIT on True and EVENT_PREDICATE_MISS on False."""
    from omicsclaw.runtime.context_layers import (
        register_predicate_event_sink,
        unregister_predicate_event_sink,
    )

    captured: list[events.LifecycleEvent] = []
    sink_id = register_predicate_event_sink(captured.append)
    try:
        inj_hit = ContextLayerInjector(
            name="probe_hit",
            order=99,
            placement="system",
            surfaces=("bot",),
            builder=_builder,
            predicate=lambda req: True,
        )
        inj_miss = ContextLayerInjector(
            name="probe_miss",
            order=99,
            placement="system",
            surfaces=("bot",),
            builder=_builder,
            predicate=lambda req: False,
        )
        assert inj_hit.applies(ContextAssemblyRequest(surface="bot")) is True
        assert inj_miss.applies(ContextAssemblyRequest(surface="bot")) is False
    finally:
        unregister_predicate_event_sink(sink_id)

    names = [evt.name for evt in captured]
    assert events.EVENT_PREDICATE_HIT in names
    assert events.EVENT_PREDICATE_MISS in names
    # Each event payload should carry at least the injector name.
    for evt in captured:
        assert evt.payload.get("predicate") in {"probe_hit", "probe_miss"}
