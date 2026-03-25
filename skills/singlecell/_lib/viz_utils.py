"""Visualization utilities for single-cell analysis."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import matplotlib.figure


def save_figure(fig: matplotlib.figure.Figure, output_dir: Path, filename: str) -> Path:
    """Save figure to output directory."""
    output_dir = Path(output_dir)
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    fig_path = fig_dir / filename
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    return fig_path
