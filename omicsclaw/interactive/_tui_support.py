"""Shared display helpers for the Textual TUI surface."""

from __future__ import annotations


def build_tui_header_label(
    *,
    model: str,
    session_id: str,
    mode: str | None = None,
) -> str:
    effective_model = model or "AI"
    mode_prefix = f"[{mode}] · " if mode else ""
    return f"{effective_model} · {mode_prefix}session {session_id}"
