"""
pileup.py — Bulk Hi-C Step 4d: aggregate / pileup analysis (coolpup.py).

    coolpup.py <mcool::res> <features> --expected <exp> --clr_weight_name weight
      loops (BEDPE) → off-diagonal APA (--flank)
      TADs  (BED)   → on-diagonal, size-normalised (--local --rescale
                      --rescale_flank 1.0 --rescale_size 99)
      boundaries (BED) → on-diagonal (--local)
    → aggregate observed/expected matrix (.clpy) + heatmap + central enrichment

Publication-clean figures via _lib/viz (pdf+png). Per-sample APA heatmaps plus,
for ≥2 samples, a side-by-side comparison panel (plot_pileup_all).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .toolrun import check, run
from . import viz

logger = logging.getLogger(__name__)

DEFAULT_FLANK = 100_000
RESCALE_SIZE = 99


@dataclass
class PileupResult:
    sample_name:    str
    resolution:     int
    features:       Path
    features_format: str
    flank:          int = DEFAULT_FLANK
    n_features:     int = 0
    pileup_npz:     Path | None = None     # coolpup .clpy output
    pileup_png:     Path | None = None
    center_enrichment: float | None = None
    kind:           str = "loops"


def _count_features(features: Path) -> int:
    try:
        with open(features) as fh:
            return sum(1 for ln in fh if ln.strip() and not ln.startswith(("#", "chrom", "BIN1")))
    except OSError:
        return 0


def _load_matrix(clpy: Path):
    import numpy as np
    from coolpuppy.lib.io import load_pileup_df
    df = load_pileup_df(str(clpy))
    return np.asarray(df["data"].iloc[0], dtype=float)


def _center_enrichment(mat) -> float | None:
    import numpy as np
    if mat.ndim != 2 or mat.size == 0:
        return None
    c = mat.shape[0] // 2
    return float(np.nanmean(mat[c - 1:c + 2, c - 1:c + 2]))


def _diverging_norm(mat):
    """TwoSlopeNorm centred on O/E = 1, robust to the data range."""
    import numpy as np
    from matplotlib.colors import TwoSlopeNorm
    finite = mat[np.isfinite(mat)]
    if finite.size == 0:
        return None
    vmax = float(np.nanpercentile(finite, 99))
    vmin = float(np.nanpercentile(finite, 1))
    vmax = max(vmax, 1.05)
    vmin = min(vmin, 0.95)
    return TwoSlopeNorm(vmin=vmin, vcenter=1.0, vmax=vmax)


def _kb_ticks(ax, n_bins: int, flank: int, kind: str) -> None:
    if kind == "tads":
        ax.set_xticks([0, n_bins // 2, n_bins - 1]); ax.set_xticklabels(["TAD start", "", "TAD end"])
        ax.set_yticks([]); ax.set_xlabel("rescaled TAD ± flank")
        return
    kb = flank / 1000
    ax.set_xticks([0, n_bins // 2, n_bins - 1])
    ax.set_xticklabels([f"-{kb:.0f} kb", "0", f"+{kb:.0f} kb"])
    ax.set_yticks([])


def _plot_pileup(clpy: Path, out_dir: Path, name: str, *, flank: int, resolution: int,
                 kind: str, n_features: int) -> tuple[Path | None, float | None]:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        viz.setup_plot_style()
        mat = _load_matrix(clpy)
        if mat.ndim != 2 or mat.size == 0:
            return None, None
        center = _center_enrichment(mat)
        fig, ax = plt.subplots(figsize=(4.4, 4))
        norm = _diverging_norm(mat)
        im = ax.imshow(mat, cmap="coolwarm", norm=norm, origin="lower")
        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label("observed / expected")
        _kb_ticks(ax, mat.shape[0], flank, kind)
        lbl = name.split(".")[0]
        ax.set_title(f"{lbl}  {kind}")
        if center is not None:
            ax.text(0.04, 0.95, f"{center:.2f}\n(n={n_features})", transform=ax.transAxes,
                    va="top", ha="left", fontsize=10,
                    bbox=dict(boxstyle="round", fc="white", ec="none", alpha=0.6))
        return viz.save_figure(fig, name, out_dir), center
    except Exception as exc:  # noqa: BLE001
        logger.warning("pileup plotting failed (%s).", exc)
        return None, None


def plot_pileup_all(results, out_dir, kind: str):
    """≥2-sample side-by-side APA panels for one feature kind (shared colour scale)."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        items = [(r.sample_name, _load_matrix(r.pileup_npz), r.center_enrichment, r.flank, r.n_features)
                 for r in results if r.kind == kind and r.pileup_npz]
        items = [it for it in items if it[1].ndim == 2 and it[1].size]
        if len(items) < 2:
            return None
        viz.setup_plot_style()
        allvals = np.concatenate([it[1][np.isfinite(it[1])].ravel() for it in items])
        from matplotlib.colors import TwoSlopeNorm
        vmax = max(float(np.nanpercentile(allvals, 99)), 1.05)
        vmin = min(float(np.nanpercentile(allvals, 1)), 0.95)
        norm = TwoSlopeNorm(vmin=vmin, vcenter=1.0, vmax=vmax)
        n = len(items)
        fig, axes = plt.subplots(1, n, figsize=(3.4 * n, 3.6))
        if n == 1:
            axes = [axes]
        im = None
        for ax, (name, mat, center, flank, nf) in zip(axes, items):
            im = ax.imshow(mat, cmap="coolwarm", norm=norm, origin="lower")
            _kb_ticks(ax, mat.shape[0], flank, kind)
            ax.set_title(f"{name}\n{center:.2f} (n={nf})" if center is not None else name)
        fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02).set_label("observed / expected")
        return viz.save_figure(fig, f"pileup_{kind}_all", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("plot_pileup_all(%s) failed (%s).", kind, exc)
        return None


def run_pileup(
    sample_name: str,
    mcool: Path,
    resolution: int,
    features: Path,
    output_dir: Path,
    *,
    features_format: str = "bedpe",
    expected_tsv: Path | None = None,
    flank: int = DEFAULT_FLANK,
    nproc: int = 8,
    kind: str = "loops",
) -> PileupResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    uri = f"{mcool}::resolutions/{resolution}"
    n_feat = _count_features(Path(features)) if Path(features).exists() else 0
    res = PileupResult(sample_name=sample_name, resolution=resolution,
                       features=features, features_format=features_format,
                       flank=flank, n_features=n_feat, kind=kind)

    clpy = output_dir / f"{sample_name}.pileup.{resolution}.clpy"
    name = f"{sample_name}.pileup.{resolution}"

    if clpy.exists():
        logger.info("  [%s] checkpoint: pileup .clpy exists — skipping coolpup", sample_name)
        res.pileup_npz = clpy
        res.pileup_png, res.center_enrichment = _plot_pileup(
            clpy, output_dir, name, flank=flank, resolution=resolution, kind=kind, n_features=n_feat)
        return res

    if not check("coolpup.py"):
        logger.warning("coolpup.py not found — skipping pileup. Run 0_setup_env_for_bulkhic.sh.")
        return res
    if not Path(features).exists() or os.path.getsize(features) == 0:
        logger.warning("pileup features missing/empty (%s) — skipping.", features)
        return res

    if expected_tsv is None or not Path(expected_tsv).exists():
        expected_tsv = output_dir / f"{sample_name}.expected_cis.{resolution}.tsv"
        try:
            run(["cooltools", "expected-cis", "-p", nproc, "-o", expected_tsv, uri],
                label=f"expected-cis [{resolution}]")
        except RuntimeError as exc:
            logger.warning("expected-cis failed (%s) — pileup will use shifted controls.", exc)
            expected_tsv = None

    fmt = "bed" if kind in ("tads", "boundaries") else features_format
    feat_path = features
    if fmt == "bedpe":
        feat_path = _bedpe6(Path(features), output_dir / f"{sample_name}.loops6.{resolution}.bedpe")
    cmd = ["coolpup.py", uri, str(feat_path), "--features_format", fmt,
           "--clr_weight_name", "weight", "-p", nproc, "-o", clpy]
    if expected_tsv:
        cmd += ["--expected", expected_tsv]
    if kind == "tads":
        cmd += ["--local", "--rescale", "--rescale_flank", "1.0", "--rescale_size", str(RESCALE_SIZE)]
    elif kind == "boundaries":
        cmd += ["--local", "--flank", flank]
    else:
        cmd += ["--flank", flank]

    try:
        run(cmd, label=f"coolpup [{resolution}] {kind} ({fmt})")
    except RuntimeError as exc:
        logger.warning("coolpup.py failed (%s).", exc)
        return res
    if clpy.exists():
        res.pileup_npz = clpy
        res.pileup_png, res.center_enrichment = _plot_pileup(
            clpy, output_dir, name, flank=flank, resolution=resolution, kind=kind, n_features=n_feat)
    return res


def _bedpe6(features: Path, out: Path) -> Path:
    """coolpup.py wants a clean 6-column double-bed; our loops BEDPE carries extra
    columns (name/FDR/scale). Write just the first 6 columns."""
    import csv
    n = 0
    with open(features) as fin, open(out, "w") as fout:
        for row in csv.reader(fin, delimiter="\t"):
            if len(row) < 6 or not row[0] or row[0].startswith(("#", "chrom")):
                continue
            fout.write("\t".join(row[0:6]) + "\n")
            n += 1
    return out if n else features
