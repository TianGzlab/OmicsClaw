"""Output style layer backed by a shared registry."""

from __future__ import annotations

from ..context_layers import ContextAssemblyRequest
from ..output_styles import render_output_style_layer


def build_output_format_layer(request: ContextAssemblyRequest) -> str | None:
    """Build output style instructions from the active profile and surface."""
    return render_output_style_layer(
        style_name=request.output_style,
        surface=request.surface,
        omicsclaw_dir=request.omicsclaw_dir,
    )
