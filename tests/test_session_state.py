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
