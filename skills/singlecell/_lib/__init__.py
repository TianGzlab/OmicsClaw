"""Single-cell analysis utilities for OmicsClaw."""

from .gallery import PlotArtifact, PlotSpec, VisualizationRecipe, render_plot_specs
from .upstream import FastqSample
from .viz import save_figure

__version__ = "0.1.0"

__all__ = [
    "FastqSample",
    "PlotArtifact",
    "PlotSpec",
    "VisualizationRecipe",
    "render_plot_specs",
    "save_figure",
]
