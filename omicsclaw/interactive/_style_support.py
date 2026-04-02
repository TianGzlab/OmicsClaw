"""Shared output-style command helpers for interactive surfaces."""

from __future__ import annotations

import shlex
from typing import Any, Mapping

from omicsclaw.runtime.output_styles import (
    DEFAULT_OUTPUT_STYLE,
    build_output_style_registry,
    get_output_style_profiles,
    normalize_output_style_name,
)

from ._session_command_support import (
    SessionCommandView,
    build_session_metadata,
    resolve_active_output_style,
)


def _format_style_usage() -> str:
    return (
        "Usage: /style | /style list | /style set <name>\n"
        "Example: /style set scientific-brief"
    )


def build_style_command_view(
    arg: str,
    *,
    session_metadata: Mapping[str, Any] | None,
    omicsclaw_dir: str = "",
) -> SessionCommandView:
    metadata = dict(session_metadata or {})
    current_style = resolve_active_output_style(metadata) or DEFAULT_OUTPUT_STYLE
    tokens = shlex.split(arg.strip()) if arg.strip() else []

    if not tokens:
        return SessionCommandView(
            output_text=(
                f"Active output style: {current_style}\n"
                "Use /style list to view available styles.\n"
                "Use /style set <name> to switch."
            ),
        )

    command = tokens[0].lower()
    if command == "list":
        profiles = get_output_style_profiles(omicsclaw_dir)
        lines = [f"Active output style: {current_style}", "", "Available output styles:"]
        for profile in profiles:
            marker = "*" if profile.name == current_style else " "
            source_label = (
                "builtin"
                if profile.source == "builtin"
                else profile.source.replace("extension:", "extension:")
            )
            lines.append(
                f"  {marker} {profile.name} - {profile.description} [{source_label}]"
            )
        lines.extend(
            (
                "",
                "Use /style set <name> to switch.",
            )
        )
        return SessionCommandView(output_text="\n".join(lines))

    if command == "set":
        if len(tokens) < 2:
            return SessionCommandView(
                output_text=_format_style_usage(),
                success=False,
            )

        requested_name = normalize_output_style_name(tokens[1])
        registry = build_output_style_registry(omicsclaw_dir)
        if requested_name not in registry:
            available = ", ".join(profile.name for profile in get_output_style_profiles(omicsclaw_dir))
            return SessionCommandView(
                output_text=(
                    f"Unknown output style: {tokens[1]}\n"
                    f"Available styles: {available}"
                ),
                success=False,
            )

        resolved = registry[requested_name]
        return SessionCommandView(
            output_text=(
                f"Active output style set to: {resolved.name}\n"
                f"{resolved.description}"
            ),
            session_metadata=build_session_metadata(
                metadata,
                active_style=resolved.name,
            ),
            replace_session_metadata=True,
        )

    return SessionCommandView(
        output_text=_format_style_usage(),
        success=False,
    )


__all__ = ["build_style_command_view"]
