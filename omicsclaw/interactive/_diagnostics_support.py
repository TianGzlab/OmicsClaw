"""Shared diagnostics command helpers for interactive surfaces."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rich.markup import escape

from omicsclaw.diagnostics import (
    build_context_report,
    build_doctor_report,
    build_usage_report,
    render_context_report,
    render_doctor_report,
    render_usage_report,
)

from ._memory_command_support import resolve_active_scoped_memory_scope
from ._plan_mode_support import build_interactive_plan_context_from_metadata
from ._session_command_support import SessionCommandView, normalize_session_metadata


def _normalize_mcp_server_names(mcp_servers: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(name).strip()
            for name in (mcp_servers or ())
            if str(name).strip()
        )
    )


def build_doctor_command_view(
    *,
    workspace_dir: str,
    pipeline_workspace: str = "",
    omicsclaw_dir: str = "",
    output_dir: str = "",
) -> SessionCommandView:
    report = build_doctor_report(
        omicsclaw_dir=omicsclaw_dir,
        workspace_dir=workspace_dir,
        pipeline_workspace=pipeline_workspace,
        output_dir=output_dir or str(Path(omicsclaw_dir) / "output"),
    )
    return SessionCommandView(
        output_text=render_doctor_report(report, markup=True),
        render_as_markup=True,
        success=report.failure_count == 0,
    )


def build_context_command_view(
    arg: str,
    *,
    messages: list[dict[str, Any]],
    session_metadata: Mapping[str, Any] | None,
    workspace_dir: str,
    pipeline_workspace: str = "",
    output_style: str = "",
    omicsclaw_dir: str = "",
    mcp_servers: tuple[str, ...] | list[str] | None = None,
    surface: str = "interactive",
) -> SessionCommandView:
    metadata = normalize_session_metadata(dict(session_metadata or {}))
    report = build_context_report(
        surface=surface,
        messages=list(messages or []),
        session_metadata=metadata,
        workspace_dir=workspace_dir,
        pipeline_workspace=pipeline_workspace,
        query=str(arg or "").strip(),
        plan_context=build_interactive_plan_context_from_metadata(metadata),
        output_style=output_style,
        scoped_memory_scope=resolve_active_scoped_memory_scope(metadata),
        omicsclaw_dir=omicsclaw_dir,
        mcp_servers=_normalize_mcp_server_names(mcp_servers),
    )
    return SessionCommandView(
        output_text=escape(render_context_report(report, markup=False)),
        render_as_markup=True,
    )


def build_usage_command_view(
    *,
    session_usage: Mapping[str, Any] | None = None,
    session_seconds: float | None = None,
) -> SessionCommandView:
    report = build_usage_report(
        session_usage=session_usage,
        session_seconds=session_seconds,
    )
    return SessionCommandView(
        output_text=escape(render_usage_report(report)),
        render_as_markup=True,
    )


__all__ = [
    "build_context_command_view",
    "build_doctor_command_view",
    "build_usage_command_view",
]
