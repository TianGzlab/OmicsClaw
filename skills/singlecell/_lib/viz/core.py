"""Core visualization helpers shared across single-cell plots."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

os.environ.setdefault("MPLBACKEND", "Agg")
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import seaborn as sns

plt.ioff()

QC_PALETTE = {
    "counts": "#15616D",
    "genes": "#FF7D00",
    "mt": "#7B2CBF",
    "ribo": "#3A86FF",
    "neutral": "#5C677D",
    "accent": "#E63946",
    "grid": "#D9D9D9",
    "background": "#FAF7F2",
    "bar": "#0A9396",
}


def apply_singlecell_theme() -> None:
    """Apply a cleaner default plotting style for single-cell figures."""
    sns.set_theme(
        style="whitegrid",
        context="notebook",
        font_scale=1.0,
        rc={
            "axes.facecolor": QC_PALETTE["background"],
            "figure.facecolor": "white",
            "axes.edgecolor": "#B8B8B8",
            "axes.labelcolor": "#222222",
            "axes.titleweight": "semibold",
            "grid.color": QC_PALETTE["grid"],
            "grid.alpha": 0.35,
            "axes.spines.top": False,
            "axes.spines.right": False,
        },
    )


def save_figure(fig: matplotlib.figure.Figure, output_dir: Path, filename: str, *, dpi: int = 200) -> Path:
    """Save a figure under ``<output_dir>/figures`` and close it."""
    output_dir = Path(output_dir)
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    fig_path = fig_dir / filename
    fig.savefig(fig_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return fig_path
