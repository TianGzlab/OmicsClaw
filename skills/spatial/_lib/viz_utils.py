"""Backward-compatible visualization utilities.

This module previously contained the entire SpatialClaw viz API.
It now delegates to the :mod:`skills.spatial._lib.viz` package.

Existing code importing from this module continues to work unchanged::

    from skills.spatial._lib.viz_utils import save_figure, non_interactive_backend

New code should import from the richer package instead::

    from skills.spatial._lib.viz import plot_features, VizParams
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path

import matplotlib

logger = logging.getLogger(__name__)

os.environ.setdefault("MPLBACKEND", "Agg")
matplotlib.use("Agg")

import matplotlib.pyplot as plt

matplotlib.use("Agg")


@contextmanager
def non_interactive_backend():
    """Context manager that ensures the Agg (non-interactive) backend is active."""
    prev = matplotlib.get_backend()
    matplotlib.use("Agg")
    try:
        yield
    finally:
        matplotlib.use(prev)


def save_figure(
    fig: plt.Figure | None,
    output_dir: str | Path,
    filename: str,
    *,
    dpi: int = 200,
    close: bool = True,
) -> Path:
    """Save a matplotlib figure to *<output_dir>/figures/<filename>*.

    Returns the path to the saved file.
    """
    output_dir = Path(output_dir)
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    path = fig_dir / filename

    if fig is None:
        fig = plt.gcf()

    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    if close:
        plt.close(fig)
    logger.info("Saved figure: %s", path)
    return path


# Re-export the new VizParams and helpers so callers can progressively adopt
# the new API without changing their import paths.
from .viz import (  # noqa: E402, F401
    PlotArtifact,
    PlotSpec,
    VizParams,
    VisualizationRecipe,
    plot_cnv,
    plot_communication,
    plot_deconvolution,
    plot_enrichment,
    plot_expression,
    plot_features,
    plot_integration,
    plot_spatial_stats,
    plot_trajectory,
    plot_velocity,
    render_plot_specs,
)
