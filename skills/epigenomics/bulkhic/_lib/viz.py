"""
viz.py — shared publication-figure helpers for the bulk Hi-C skills.

Mirrors the bulk-ATAC convention (skills/epigenomics/bulkatac/_lib/DA.py):
a single plot style + a save helper that writes BOTH pdf and png. Skills call
``setup_plot_style()`` once, build their figure, then ``save_figure(fig, name,
out_dir)``. One-vs-many handling follows bulkatac's ``is_single`` naming:
per-sample figures are ``<sample>.<plot>``; cross-sample overlays are ``<plot>_all``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Stable, color-blind-friendly palette (Okabe-Ito) for overlaying samples.
PALETTE = ["#4C72B0", "#55A868", "#C44E52", "#8172B3", "#CCB974", "#64B5CD",
           "#E69F00", "#000000", "#999999", "#F0E442"]


def setup_plot_style() -> None:
    """Publication-clean matplotlib defaults (Agg backend, 300 dpi)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 300, "savefig.dpi": 300,
        "font.size": 11, "axes.titlesize": 12, "axes.labelsize": 11,
        "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10,
        "axes.spines.top": True, "axes.spines.right": True,
        "legend.frameon": False, "figure.autolayout": False,
        "svg.fonttype": "none", "pdf.fonttype": 42,
    })


def save_figure(fig, name: str, out_dir: Path) -> Path | None:
    """Save *fig* as both <name>.pdf and <name>.png in *out_dir*; return the png path."""
    try:
        import matplotlib.pyplot as plt
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        png = out_dir / f"{name}.png"
        for ext in ("pdf", "png"):
            fig.savefig(out_dir / f"{name}.{ext}", bbox_inches="tight")
        plt.close(fig)
        return png
    except Exception as exc:  # noqa: BLE001
        logger.warning("save_figure(%s) failed (%s).", name, exc)
        try:
            import matplotlib.pyplot as plt
            plt.close(fig)
        except Exception:  # noqa: BLE001
            pass
        return None


def sample_colors(samples: list[str]) -> dict:
    """Map each sample to a stable color (by order)."""
    return {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(samples)}


def condition_of(sample: str, sample_sheet=None) -> str:
    """Best-effort biological condition for a sample.

    Uses the sample sheet's ``condition`` when available; otherwise strips
    ``Combined`` / ``_rep<N>`` / trailing digits from the sample name
    (ctrlCombined→ctrl, tcdd2→tcdd, async_rep1→async, arrest_rep2→arrest).
    """
    try:
        if sample_sheet:
            rows = sample_sheet.values() if isinstance(sample_sheet, dict) else sample_sheet
            for r in rows:
                if isinstance(r, dict) and r.get("sample") == sample and r.get("condition"):
                    return str(r["condition"])
            if isinstance(sample_sheet, dict) and isinstance(sample_sheet.get(sample), dict):
                c = sample_sheet[sample].get("condition")
                if c:
                    return str(c)
    except Exception:  # noqa: BLE001
        pass
    s = re.sub(r"[_\-]?[Cc]ombined$", "", sample)
    s = re.sub(r"[_\-]?rep\d+$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\d+$", "", s)
    return s.strip("_-") or sample


def violin_size(df, out_dir, name, *, ylabel, title):
    """Violin per condition with a THIN inner boxplot (IQR box + median +
    whiskers + outlier points). One violin per condition, coloured by condition,
    with the per-condition count in the x tick labels. Used for the loop-size and
    TAD-size figures (mirrors the production MS log10 size violins).
    """
    try:
        import numpy as np
        import matplotlib.pyplot as plt
        setup_plot_style()
        order = list(dict.fromkeys(df["condition"]))
        colors = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(order)}
        data = [np.asarray(df.loc[df["condition"] == c, "log10size"].values, dtype=float) for c in order]
        data = [d[np.isfinite(d)] for d in data]
        if not any(len(d) >= 2 for d in data):
            return None
        pos = list(range(1, len(order) + 1))
        fig, ax = plt.subplots(figsize=(0.95 * len(order) + 2.4, 4))
        # violin body only
        parts = ax.violinplot(data, positions=pos, showmeans=False,
                              showmedians=False, showextrema=False, widths=0.8)
        for i, b in enumerate(parts["bodies"]):
            b.set_facecolor(colors[order[i]]); b.set_edgecolor("0.30")
            b.set_alpha(0.65); b.set_linewidth(0.8)
        # thin inner boxplot: IQR box + median + whiskers + outliers
        ax.boxplot(
            data, positions=pos, widths=0.10, showfliers=True, patch_artist=True,
            medianprops=dict(color="white", linewidth=1.3),
            boxprops=dict(facecolor="0.22", edgecolor="0.22", linewidth=0),
            whiskerprops=dict(color="0.22", linewidth=1.0),
            capprops=dict(color="0.22", linewidth=1.0),
            flierprops=dict(marker="o", markersize=2.2, markerfacecolor="0.35",
                            markeredgecolor="none", alpha=0.45))
        ax.set_xticks(pos)
        ax.set_xticklabels([f"{c}\n(n={len(data[i]):,})" for i, c in enumerate(order)])
        ax.set_ylabel(ylabel); ax.set_xlabel(""); ax.set_title(title)
        return save_figure(fig, name, out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("violin_size(%s) failed (%s).", name, exc)
        return None
