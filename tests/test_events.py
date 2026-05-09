"""Lifecycle event constants tests.

Phase 1 (Task 1.2) of the system-prompt-compression refactor adds
EVENT_PREDICATE_HIT and EVENT_PREDICATE_MISS so that the predicate-gated
context layer machinery (Phase 4) can record which conditional rules
fired or were skipped.
"""

from __future__ import annotations

from omicsclaw.runtime import events


def test_predicate_hit_event_constant_exists() -> None:
    assert events.EVENT_PREDICATE_HIT == "predicate_hit"


def test_predicate_miss_event_constant_exists() -> None:
    assert events.EVENT_PREDICATE_MISS == "predicate_miss"


def test_predicate_events_are_in_valid_lifecycle_events() -> None:
    assert events.EVENT_PREDICATE_HIT in events.VALID_LIFECYCLE_EVENTS
    assert events.EVENT_PREDICATE_MISS in events.VALID_LIFECYCLE_EVENTS


def test_predicate_events_exported_in_all() -> None:
    assert "EVENT_PREDICATE_HIT" in events.__all__
    assert "EVENT_PREDICATE_MISS" in events.__all__


def test_lifecycle_event_accepts_predicate_event_names() -> None:
    hit = events.LifecycleEvent(
        name=events.EVENT_PREDICATE_HIT,
        payload={"predicate": "workspace_active", "request_surface": "bot"},
    )
    miss = events.LifecycleEvent(
        name=events.EVENT_PREDICATE_MISS,
        payload={"predicate": "anndata_or_file_path_in_query"},
    )
    assert hit.to_dict()["name"] == "predicate_hit"
    assert miss.to_dict()["name"] == "predicate_miss"
