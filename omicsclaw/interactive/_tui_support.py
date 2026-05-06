"""Shared display helpers for the Textual TUI surface."""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


def build_tui_header_label(
    *,
    model: str,
    session_id: str,
    mode: str | None = None,
) -> str:
    effective_model = model or "AI"
    mode_prefix = f"[{mode}] · " if mode else ""
    return f"{effective_model} · {mode_prefix}session {session_id}"


def attach_reasoning_container(
    chat: Any,
    *,
    collapsible_cls: type[Any],
    vertical_cls: type[T],
    title: str = "Agent Reasoning & Tool Execution",
) -> T:
    """Attach a reasoning panel without mounting children before the parent."""
    collapsible = collapsible_cls(title=title)
    container = vertical_cls()
    chat.mount(collapsible)
    collapsible.mount(container)
    return container
