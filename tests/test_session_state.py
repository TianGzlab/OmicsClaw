"""Invariant tests for the typed ``SessionState`` module that replaces the
``state: dict[str, Any]`` pattern in ``omicsclaw/interactive/interactive.py``.

These tests exercise the dataclass shape, defaults, invariants, and the
to_dict/from_dict adapter used during the staged migration.
"""

from __future__ import annotations

from typing import Any

import pytest

from omicsclaw.interactive._session_state import SessionState


# --- Construction & defaults --------------------------------------------------

def test_session_state_required_fields_have_no_default():
    """``session_id``, ``workspace_dir``, ``ui_backend`` are required."""
    with pytest.raises(TypeError):
        SessionState()  # type: ignore[call-arg]


def test_session_state_optional_fields_have_documented_defaults():
    s = SessionState(session_id="sess-1", workspace_dir="/tmp/x", ui_backend="cli")
    assert s.pipeline_workspace == ""
    assert s.session_metadata == {}
    assert s.messages == []
    assert s.running is True
    assert s.tips_enabled is True
    assert s.tips_level == "verbose"


def test_session_state_default_collections_are_independent_per_instance():
    """Mutable defaults must not leak across instances (avoid the classic
    ``messages=[]`` shared-default footgun)."""
    a = SessionState(session_id="a", workspace_dir="/x", ui_backend="cli")
    b = SessionState(session_id="b", workspace_dir="/y", ui_backend="tui")
    a.messages.append({"role": "user", "content": "hi"})
    a.session_metadata["k"] = "v"
    assert b.messages == []
    assert b.session_metadata == {}


# --- to_dict / from_dict adapter ----------------------------------------------

def test_to_dict_round_trips_through_from_dict():
    original = SessionState(
        session_id="sess-rt",
        workspace_dir="/wkspace",
        ui_backend="tui",
        pipeline_workspace="/wkspace/pipeline-001",
        session_metadata={"title": "demo run"},
        messages=[{"role": "user", "content": "hi"}],
        running=False,
        tips_enabled=False,
        tips_level="short",
    )
    dumped = original.to_dict()
    restored = SessionState.from_dict(dumped)
    assert restored == original


def test_to_dict_emits_keys_matching_legacy_state_dict():
    """Migration adapter: the dumped dict must use the exact keys interactive.py
    historically used so partially-migrated callers still see a familiar shape."""
    s = SessionState(session_id="x", workspace_dir="/w", ui_backend="cli")
    d = s.to_dict()
    assert set(d) >= {
        "session_id",
        "workspace_dir",
        "ui_backend",
        "pipeline_workspace",
        "session_metadata",
        "messages",
        "running",
        "tips_enabled",
        "tips_level",
    }


def test_from_dict_tolerates_absent_optional_fields():
    """Legacy state dicts often omit ``tips_enabled`` / ``tips_level`` until
    the user toggles them; ``from_dict`` must absorb that shape."""
    legacy = {
        "session_id": "legacy",
        "workspace_dir": "/legacy",
        "ui_backend": "cli",
        "pipeline_workspace": "",
        "session_metadata": {},
        "messages": [],
        "running": True,
        # tips_enabled / tips_level intentionally absent
    }
    s = SessionState.from_dict(legacy)
    assert s.tips_enabled is True
    assert s.tips_level == "verbose"


def test_from_dict_rejects_missing_required_fields():
    """Required fields with no safe default must raise rather than coerce."""
    with pytest.raises((KeyError, TypeError)):
        SessionState.from_dict({"workspace_dir": "/w", "ui_backend": "cli"})


# --- Transitions --------------------------------------------------------------

def test_stop_marks_session_not_running():
    s = SessionState(session_id="x", workspace_dir="/w", ui_backend="cli")
    assert s.running is True
    s.stop()
    assert s.running is False


def test_set_tips_enabled_toggles_the_flag():
    s = SessionState(session_id="x", workspace_dir="/w", ui_backend="cli")
    s.set_tips(enabled=False)
    assert s.tips_enabled is False
    s.set_tips(enabled=True)
    assert s.tips_enabled is True


def test_set_tips_level_validates_input():
    """Only ``verbose`` / ``short`` / ``off`` are valid levels (matching the
    /tips slash command's accepted values). Other inputs must raise so a
    typo never silently leaves the session in a malformed state."""
    s = SessionState(session_id="x", workspace_dir="/w", ui_backend="cli")
    s.set_tips(level="short")
    assert s.tips_level == "short"
    s.set_tips(level="off")
    assert s.tips_level == "off"
    with pytest.raises(ValueError):
        s.set_tips(level="not-a-level")


def test_set_tips_with_none_arguments_is_idempotent():
    """``set_tips()`` with no kwargs (or all-None) must be a no-op so callers
    that forward optional CLI args don't accidentally clear the level."""
    s = SessionState(
        session_id="x", workspace_dir="/w", ui_backend="cli",
        tips_enabled=False, tips_level="off",
    )
    s.set_tips()
    assert s.tips_enabled is False
    assert s.tips_level == "off"
    s.set_tips(enabled=None, level=None)
    assert s.tips_enabled is False
    assert s.tips_level == "off"


def test_set_pipeline_workspace_normalizes_none_to_empty_string():
    """The legacy state dict stored ``""`` for "no active workspace"; the
    helper accepts None for ergonomics and coerces to that representation."""
    s = SessionState(session_id="x", workspace_dir="/w", ui_backend="cli")
    s.set_pipeline_workspace("/some/path")
    assert s.pipeline_workspace == "/some/path"
    s.set_pipeline_workspace(None)
    assert s.pipeline_workspace == ""
    s.set_pipeline_workspace("")
    assert s.pipeline_workspace == ""
