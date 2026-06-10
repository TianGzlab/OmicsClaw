"""
insulation.py — Bulk Hi-C Step 4b: TADs / insulation (cooltools).

    cooltools insulation --threshold Li --view <main-chroms> <mcool::res> <window…>
      → per-bin insulation score + boundary calls + boundary strength (multi-window)
      → boundaries BED (bins flagged is_boundary at the primary window)
      → TAD domains BED  (boundaries → domains, small TADs merged across the
        weaker boundary; mirrors production utils.extract_TADs)

Insulation/TADs are mid-resolution — default 25 kb with windows 5×/10×/25× the
resolution. Degrades gracefully if cooltools is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .toolrun import check, run
from . import viz

logger = logging.getLogger(__name__)

DEFAULT_RESOLUTION = 25_000
DEFAULT_RESOLUTIONS = [5_000, 10_000, 25_000, 50_000]   # MS TAD resolutions
DEFAULT_WINDOW_MULTIPLES = (8,)          # MS: single diamond window = 8 × resolution
MAX_TAD_LENGTH = 3_000_000


@dataclass
class InsulationResult:
    sample_name:    str
    resolution:     int
    is_combined:    bool = False
    windows:        list[int] = field(default_factory=list)
    primary_window: int = 0
    insulation_tsv: Path | None = None
    boundaries_bed: Path | None = None
    n_boundaries:   int = 0
    tads_bed:       Path | None = None
    n_tads:         int = 0


def _primary_window(windows: list[int]) -> int:
    """Median window — the one used for boundary/TAD calling."""
    ws = sorted(windows)
    return ws[len(ws) // 2]


def _boundaries_bed(insulation_tsv: Path, window: int, out_bed: Path) -> tuple[Path | None, int]:
    """Extract boundary bins (is_boundary_<window> == True) → BED4."""
    try:
        import pandas as pd
        df = pd.read_csv(insulation_tsv, sep="\t")
        bcol = f"is_boundary_{window}"
        scol = f"boundary_strength_{window}"
        if bcol not in df.columns or not {"chrom", "start", "end"} <= set(df.columns):
            bcol = next((c for c in df.columns if c.startswith("is_boundary_")), None)
            scol = next((c for c in df.columns if c.startswith("boundary_strength_")), None)
            if bcol is None:
                return None, 0
        sub = df[df[bcol] == True].copy()  # noqa: E712
        cols = ["chrom", "start", "end"] + ([scol] if scol in df.columns else [])
        sub[cols].to_csv(out_bed, sep="\t", header=False, index=False)
        return out_bed, len(sub)
    except Exception as exc:  # noqa: BLE001
        logger.warning("boundary extraction failed (%s).", exc)
        return None, 0


def _extract_tads(insulation_tsv: Path, window: int, out_bed: Path, *,
                  max_TAD_length: int = MAX_TAD_LENGTH,
                  min_TAD_length: int | None = None) -> tuple[Path | None, int]:
    """Boundaries → TAD domains, merging small TADs across the WEAKER boundary.

    Ports production 2_TADs_V2/codes/utils.py:extract_TADs (merge_strategy=
    'weaker_boundary'). A TAD is the span between consecutive boundary midpoints
    (and chrom ends); TADs longer than max_TAD_length are dropped; TADs shorter
    than min_TAD_length are merged into the neighbour across whichever flanking
    boundary is weaker.
    """
    try:
        import pandas as pd
        df = pd.read_csv(insulation_tsv, sep="\t")
        bcol = f"is_boundary_{window}"
        scol = f"boundary_strength_{window}"
        if bcol not in df.columns:
            bcol = next((c for c in df.columns if c.startswith("is_boundary_")), None)
            scol = next((c for c in df.columns if c.startswith("boundary_strength_")), None)
        if bcol is None or not {"chrom", "start", "end"} <= set(df.columns):
            return None, 0
        if min_TAD_length is None:
            min_TAD_length = 3 * window

        bnd = df[df[bcol] == True].copy()  # noqa: E712
        boundary_mid: dict = {}
        strength: dict = {}
        for _, row in bnd.iterrows():
            ch = row["chrom"]; mid = int((row["start"] + row["end"]) // 2)
            boundary_mid.setdefault(ch, []).append(mid)
            if scol and scol in row:
                strength[(ch, mid)] = row[scol]
        for ch in boundary_mid:
            boundary_mid[ch].sort()

        tad_list = []
        for ch in df["chrom"].unique():
            cd = df[df["chrom"] == ch]
            cstart = int(cd["start"].min()); cend = int(cd["end"].max())
            bs = boundary_mid.get(ch, [])
            if not bs:
                tad_list.append({"chrom": ch, "start": cstart, "end": cend}); continue
            tad_list.append({"chrom": ch, "start": cstart, "end": bs[0]})
            for i in range(len(bs) - 1):
                tad_list.append({"chrom": ch, "start": bs[i], "end": bs[i + 1]})
            tad_list.append({"chrom": ch, "start": bs[-1], "end": cend})

        tads = pd.DataFrame(tad_list)
        if tads.empty:
            return None, 0
        tads = tads[(tads["end"] - tads["start"]) <= max_TAD_length].copy()

        final = []
        inf = float("inf")
        for ch in tads["chrom"].unique():
            ct = tads[tads["chrom"] == ch].sort_values("start").reset_index(drop=True)
            merged: list = []
            i = 0
            while i < len(ct):
                cur = ct.iloc[i].to_dict()
                length = cur["end"] - cur["start"]
                if length >= min_TAD_length:
                    merged.append(cur); i += 1; continue
                has_left = len(merged) > 0
                has_right = i < len(ct) - 1
                if has_left and has_right:
                    ls = strength.get((ch, merged[-1]["end"]), inf)
                    rs = strength.get((ch, cur["end"]), inf)
                    if ls <= rs:
                        merged[-1]["end"] = cur["end"]
                    else:
                        cur["end"] = int(ct.iloc[i + 1]["end"]); merged.append(cur); i += 1
                elif has_left:
                    merged[-1]["end"] = cur["end"]
                elif has_right:
                    cur["end"] = int(ct.iloc[i + 1]["end"]); merged.append(cur); i += 1
                else:
                    merged.append(cur)
                i += 1
            final.extend(merged)

        tads = pd.DataFrame(final)[["chrom", "start", "end"]]
        tads = tads.astype({"start": int, "end": int})
        tads.to_csv(out_bed, sep="\t", header=False, index=False)
        return out_bed, len(tads)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TAD extraction failed (%s).", exc)
        return None, 0


def _make_view(uri, min_size, out_path):
    """Viewframe of chromosomes >= min_size bp.

    dm6 (and many assemblies) ship hundreds of sub-kb unplaced scaffolds smaller
    than the diamond window; cooltools insul_diamond crashes on them (IndexError
    in cooler.annotate). Restricting the view to assembled chromosomes large
    enough to hold the window avoids that and is standard practice.
    """
    try:
        import cooler
        import pandas as pd
        sizes = cooler.Cooler(uri).chromsizes
        keep = sizes[sizes >= min_size]
        if keep.empty:
            return None
        out_path = Path(out_path)
        if out_path.exists():
            return out_path
        view = pd.DataFrame({"chrom": keep.index, "start": 0,
                             "end": keep.values, "name": keep.index})
        view.to_csv(out_path, sep="\t", header=False, index=False)
        return out_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("view construction failed (%s) - running without --view.", exc)
        return None


def run_insulation(
    sample_name: str,
    mcool: Path,
    resolution: int,
    output_dir: Path,
    *,
    windows: list[int] | None = None,
    threshold: str = "Li",
    nproc: int = 8,  # noqa: ARG001 — cooltools insulation is single-process
    is_combined: bool = False,
) -> InsulationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    windows = windows or [m * resolution for m in DEFAULT_WINDOW_MULTIPLES]
    primary = _primary_window(windows)
    uri = f"{mcool}::resolutions/{resolution}"
    res = InsulationResult(sample_name=sample_name, resolution=resolution,
                           windows=windows, primary_window=primary, is_combined=is_combined)
    tsv = output_dir / f"{sample_name}.insulation.{resolution}.tsv"

    def _derive(tsv_path: Path) -> None:
        res.insulation_tsv = tsv_path
        bed, n = _boundaries_bed(tsv_path, primary, output_dir / f"{sample_name}.boundaries.{resolution}.bed")
        res.boundaries_bed, res.n_boundaries = bed, n
        tbed, nt = _extract_tads(tsv_path, primary, output_dir / f"{sample_name}.TADs.{resolution}.bed",
                                 min_TAD_length=primary // 2)
        res.tads_bed, res.n_tads = tbed, nt

    # Checkpoint: reuse a completed insulation TSV (delete it to force a re-run).
    if tsv.exists() and tsv.stat().st_size > 0:
        logger.info("  [%s] checkpoint: insulation TSV exists — skipping cooltools", sample_name)
        _derive(tsv)
        return res

    if not check("cooltools"):
        logger.warning("cooltools not found — skipping insulation.")
        return res

    cmd = ["cooltools", "insulation", "--threshold", threshold, "-o", tsv]
    # `--bigwig` shells out to UCSC bedGraphToBigWig; only request it if present.
    if check("bedGraphToBigWig"):
        cmd.append("--bigwig")
    # Floor the view at >=1 Mb (not just the window): at fine resolutions the diamond
    # window is small (e.g. 40 kb @ 5 kb) and dm6 small scaffolds slip in -> insul_diamond
    # IndexError. Keep only chromosomes comfortably larger than the window.
    _view = _make_view(uri, max(max(windows) * 5, 1_000_000), output_dir / f"view.{resolution}.bed")
    if _view is not None:
        cmd += ["--view", str(_view)]
    cmd.append(uri)
    cmd += [str(w) for w in windows]
    try:
        run(cmd, label=f"insulation [{resolution}] windows={windows}")
    except RuntimeError as exc:
        logger.warning("insulation failed (%s).", exc)
        return res

    if tsv.exists():
        _derive(tsv)
    return res


def _plot_tad_pca(scores, var, names, out_dir, sample_sheet, resolution, window, n_bins):
    try:
        import numpy as np
        import matplotlib.pyplot as plt
        viz.setup_plot_style()
        conds = [viz.condition_of(n, sample_sheet) for n in names]
        ucond = list(dict.fromkeys(conds))
        ccolor = {c: viz.PALETTE[i % len(viz.PALETTE)] for i, c in enumerate(ucond)}
        pc1 = scores[:, 0]
        pc2 = scores[:, 1] if scores.shape[1] > 1 else np.zeros_like(pc1)
        res_lab = f"{resolution // 1000} kb" if resolution % 1000 == 0 else f"{resolution} bp"
        fig, ax = plt.subplots(figsize=(5, 4.5))
        seen = set()
        for i, n in enumerate(names):
            c = conds[i]
            ax.scatter(pc1[i], pc2[i], color=ccolor[c], s=40, edgecolor="white", lw=0.5,
                       zorder=3, label=c if c not in seen else None)
            seen.add(c)
            ax.annotate(n, (pc1[i], pc2[i]), fontsize=8, xytext=(4, 4), textcoords="offset points")
        ax.axhline(0, color="grey", lw=0.5, ls=":")
        ax.axvline(0, color="grey", lw=0.5, ls=":")
        ax.set_xlabel(f"PC1 ({var[0] * 100:.0f}%)")
        ax.set_ylabel(f"PC2 ({var[1] * 100:.0f}%)" if len(var) > 1 else "PC2")
        ax.set_title(f"TAD insulation PCA ({res_lab}, win {window // 1000}kb, {n_bins} bins)")
        ax.legend()
        return viz.save_figure(fig, "tad_pca", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TAD PCA plot failed (%s).", exc)
        return None


def run_tad_pca(results, out_dir, *, resolution, window, sample_sheet=None):
    """Sample PCA on per-bin log2 insulation scores (the TAD profile).

    Builds a (bins x samples) matrix of cooltools' ``log2_insulation_score_<window>``
    (the diamond-window insulation / "TAD score"), quantile-normalizes across
    samples, then PCA (numpy SVD) across samples -> a PC1/PC2 scatter coloured by
    condition. Asks whether samples separate by their genome-wide TAD/insulation
    profile.

    Sources / method:
      * Insulation score (diamond-window) for TAD boundary detection - Crane et al.,
        Nature 2015 (doi:10.1038/nature14450).
      * Clustering / PCA of samples on insulation-boundary scores (replicates
        co-cluster) - HiC-bench, Lazaris et al., BMC Genomics 2017
        (doi:10.1186/s12864-016-3387-6). The production MS pipeline clusters the
        same `log2_insulation_score` feature (ward linkage on correlation distance);
        here we PCA-project it.
      * Quantile normalization - Bolstad et al., Bioinformatics 2003
        (doi:10.1093/bioinformatics/19.2.185).
    """
    try:
        import numpy as np
        import pandas as pd
        from .compartments import _quantile_normalize
    except Exception as exc:  # noqa: BLE001
        logger.warning("deps unavailable (%s) — no TAD PCA.", exc)
        return None
    if len(results) < 3:
        logger.info("TAD PCA skipped (need >=3 samples for a 2D embedding).")
        return None
    try:
        target = f"log2_insulation_score_{window}"
        cols = {}
        for r in results:
            tsv = getattr(r, "insulation_tsv", None)
            if not tsv or not Path(tsv).exists():
                continue
            df = pd.read_csv(tsv, sep="\t")
            col = target if target in df.columns else next(
                (c for c in df.columns if c.startswith("log2_insulation_score")), None)
            if col is None or not {"chrom", "start"} <= set(df.columns):
                continue
            vals = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
            key = df["chrom"].astype(str) + ":" + df["start"].astype(str)
            cols[r.sample_name] = pd.Series(vals.values, index=key)
        if len(cols) < 3:
            return None
        mat = pd.DataFrame(cols).dropna()          # bins x samples, common finite bins
        if mat.shape[0] < 2:
            return None
        names = list(mat.columns)
        Xn = _quantile_normalize(mat.values)
        Xc = Xn.T - Xn.T.mean(axis=0, keepdims=True)
        U, S, _ = np.linalg.svd(Xc, full_matrices=False)
        scores = U * S
        var = (S ** 2) / np.sum(S ** 2) if np.sum(S ** 2) > 0 else np.zeros_like(S)
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        ncomp = min(scores.shape[1], 5)
        pd.DataFrame(scores[:, :ncomp], index=names,
                     columns=[f"PC{i + 1}" for i in range(ncomp)]).to_csv(
            out_dir / "tad_pca_coords.tsv", sep="\t")
        png = _plot_tad_pca(scores, var, names, out_dir, sample_sheet, resolution, window, mat.shape[0])
        return {"png": str(png) if png else None,
                "coords": str(out_dir / "tad_pca_coords.tsv"),
                "var": [float(v) for v in var[:2]], "n_bins": int(mat.shape[0])}
    except Exception as exc:  # noqa: BLE001
        logger.warning("TAD PCA failed (%s).", exc)
        return None


def plot_tad_size_distribution(results, out_dir, *, resolution=None, sample_sheet=None):
    """TAD size as a VIOLIN per condition (log10 bp).

    Pass the condition (combined) samples only; x labels carry each condition's
    TAD count. Mirrors the production MS log10 size violins.
    """
    try:
        import numpy as np
        import pandas as pd
        rows = []
        for r in results:
            cond = viz.condition_of(r.sample_name, sample_sheet)
            tb = getattr(r, "tads_bed", None)
            if not tb or not Path(tb).exists() or Path(tb).stat().st_size == 0:
                continue
            try:
                df0 = pd.read_csv(tb, sep="\t", header=None)
                sizes = (df0[2] - df0[1]).astype(float)
                sizes = sizes[sizes > 0]
            except Exception:  # noqa: BLE001
                continue
            for s in sizes:
                rows.append((cond, float(np.log10(s))))
        if len(rows) < 2:
            return None
        df = pd.DataFrame(rows, columns=["condition", "log10size"])
        rl = f" @ {resolution // 1000} kb" if resolution else ""
        return viz.violin_size(df, out_dir, "tad_size_distribution",
                               ylabel="log10 TAD size (bp)", title=f"TAD size{rl}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("tad_size_distribution failed (%s).", exc)
        return None


def plot_insulation_all(results, out_dir):
    """≥2-sample comparison: boundary/TAD counts bar + TAD-size distribution."""
    try:
        import numpy as np
        import pandas as pd
        import matplotlib.pyplot as plt
        if len(results) < 2:
            return None
        viz.setup_plot_style()
        names = [r.sample_name for r in results]
        colors = viz.sample_colors(names)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4))
        x = np.arange(len(names)); w = 0.38
        ax1.bar(x - w / 2, [r.n_boundaries for r in results], w, label="boundaries", color="#4C72B0")
        ax1.bar(x + w / 2, [r.n_tads for r in results], w, label="TADs", color="#55A868")
        ax1.set_xticks(x); ax1.set_xticklabels(names, rotation=45, ha="right")
        ax1.set_ylabel("count"); ax1.set_title("Boundaries / TADs"); ax1.legend()
        plotted = False
        for r in results:
            tb = getattr(r, "tads_bed", None)
            if not tb or not Path(tb).exists() or Path(tb).stat().st_size == 0:
                continue
            try:
                df = pd.read_csv(tb, sep="\t", header=None)
                sizes = (df[2] - df[1]) / 1000.0
                sizes = sizes[sizes > 0]
            except Exception:  # noqa: BLE001
                continue
            if len(sizes):
                ax2.hist(np.log10(sizes), bins=40, histtype="step", lw=2, density=True,
                         color=colors[r.sample_name], label=r.sample_name)
                plotted = True
        ax2.set_xlabel("log10 TAD size (kb)"); ax2.set_ylabel("density")
        ax2.set_title("TAD size distribution")
        if plotted:
            ax2.legend()
        return viz.save_figure(fig, "insulation_all", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("insulation_all failed (%s).", exc)
        return None
