"""
compartments.py — Bulk Hi-C Step 4a: A/B compartments (cooltools).

    main-chromosome view (drop sub-window scaffolds that corrupt E1/expected)
    GC track (bioframe.frac_gc on the cooler bins, for eigenvector phasing)
    cooltools expected-cis  --view → expected.tsv
    cooltools eigs-cis --view --phasing-track GC  → E1 (GC-phased: + = A, − = B)
    cooltools saddle   --view → compartment-strength matrix + heatmap
    compartment-strength scalar  (AA·BB)/AB²  from the saddle quantile corners

Compartments emerge at coarse resolution — default 100 kb (expose via the
skill's --resolution). All steps degrade gracefully if cooltools/bioframe are
unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .toolrun import check, run
from . import viz

logger = logging.getLogger(__name__)

DEFAULT_RESOLUTION = 100_000
DEFAULT_RESOLUTIONS = [10_000, 25_000, 50_000, 100_000]


@dataclass
class CompartmentResult:
    sample_name:  str
    resolution:   int
    is_combined:  bool = False
    gc_track:     Path | None = None
    view_bed:     Path | None = None
    expected_tsv: Path | None = None
    eigs_vecs:    Path | None = None      # E1 (+ further eigenvectors) per bin
    eigs_lam:     Path | None = None      # eigenvalues
    ab_bed:       Path | None = None      # A/B compartment BED (E1 sign)
    saddle_npz:   Path | None = None
    saddle_png:   Path | None = None
    strength_tsv: Path | None = None      # AA/BB/AB/strength table
    strength:     float | None = None     # (AA·BB)/AB² compartmentalisation strength
    aa:           float | None = None
    bb:           float | None = None
    ab:           float | None = None


def _make_chrom_view(cooler_uri: str, out_path: Path, *, min_size: int) -> Path | None:
    """Viewframe (chrom,start,end,name) of chromosomes >= min_size bp.

    Drops the hundreds of sub-kb unplaced scaffolds (chrUn_*/_random) that
    otherwise skew expected-cis / eigs-cis / saddle. Mirrors the production
    pipeline's explicit main-chromosome view.
    """
    try:
        import cooler
        import pandas as pd
        sizes = cooler.Cooler(cooler_uri).chromsizes
        keep = sizes[sizes >= min_size]
        if keep.empty:
            return None
        view = pd.DataFrame({"chrom": keep.index, "start": 0,
                             "end": keep.values, "name": keep.index})
        view.to_csv(out_path, sep="\t", header=False, index=False)
        logger.info("compartment view: %d chrom(s) >= %d bp", len(keep), min_size)
        return out_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("chrom view failed (%s) — running without --view.", exc)
        return None


def make_gc_track(cooler_uri: str, fasta: Path, out_tsv: Path, *, view_bed: Path | None = None) -> Path | None:
    """Write a per-bin GC-content track (chrom,start,end,GC) matching the cooler bins.

    Restricted to the main-chromosome view when ``view_bed`` is given. This is
    essential at coarse resolutions: dm6-style assemblies have hundreds of small
    unplaced scaffolds, each contributing one *partial* bin; cooltools infers the
    track resolution from the MEDIAN bin width, so unfiltered partial bins make
    the median < binsize and eigs-cis aborts with a track/cooler size mismatch.
    """
    try:
        import bioframe
        import cooler
    except Exception as exc:  # noqa: BLE001
        logger.warning("cooler/bioframe unavailable (%s) — cannot build GC phasing track.", exc)
        return None
    try:
        clr = cooler.Cooler(cooler_uri)
        bins = clr.bins()[:][["chrom", "start", "end"]]
        if view_bed and Path(view_bed).exists():
            import pandas as pd
            keep = set(pd.read_csv(view_bed, sep="\t", header=None)[0].astype(str))
            bins = bins[bins["chrom"].astype(str).isin(keep)].reset_index(drop=True)
        fa = bioframe.load_fasta(str(fasta))
        gc = bioframe.frac_gc(bins, fa)
        gc.to_csv(out_tsv, sep="\t", index=False)
        logger.info("GC phasing track: %s (%d bins)", out_tsv, len(gc))
        return out_tsv
    except Exception as exc:  # noqa: BLE001
        logger.warning("GC track computation failed (%s) — eigs will run unphased.", exc)
        return None


def _ab_bed_from_vecs(vecs_tsv: Path, out_bed: Path) -> Path | None:
    """Binarise E1 → A (E1>0) / B (E1<0) BED4."""
    try:
        import pandas as pd
        df = pd.read_csv(vecs_tsv, sep="\t")
        e1col = "E1" if "E1" in df.columns else next((c for c in df.columns if c.upper().startswith("E1")), None)
        if e1col is None or not {"chrom", "start", "end"} <= set(df.columns):
            return None
        df = df.dropna(subset=[e1col])
        df["compartment"] = df[e1col].apply(lambda v: "A" if v > 0 else "B")
        df[["chrom", "start", "end", "compartment"]].to_csv(out_bed, sep="\t", header=False, index=False)
        return out_bed
    except Exception as exc:  # noqa: BLE001
        logger.warning("A/B BED derivation failed (%s).", exc)
        return None


def _compartment_strength(saddle_npz: Path, out_tsv: Path) -> tuple[Path | None, dict | None]:
    """Compartmentalisation strength from the saddle quantile matrix.

    saddledata is the mean obs/exp per E1-quantile pair (cooltools CLI); drop
    the two flanking outlier bins, then corners give AA (active-active),
    BB (inactive-inactive), AB (active-inactive). strength = (AA·BB)/AB².
    Mirrors production 2c_compartmentStrength_boxplot.py:calculate_compartment_strength.
    """
    try:
        import numpy as np
        d = np.load(saddle_npz, allow_pickle=True)
        if "saddledata" not in d.files:
            logger.warning("saddle npz missing saddledata — no strength.")
            return None, None
        # cooltools CLI `saddledata` is ALREADY the mean obs/exp per E1-quantile
        # pair (saddlecounts is the pixel count) — use it directly, do NOT divide.
        saddle = np.asarray(d["saddledata"], dtype=float)
        sc = saddle[1:-1, 1:-1]  # drop flanking (outlier) quantile bins
        if sc.size == 0:
            return None, None
        BB = float(sc[0, 0]); AA = float(sc[-1, -1]); AB = float(sc[-1, 0])
        strength = (AA * BB) / (AB ** 2) if AB else float("nan")
        out_tsv.write_text(
            "AA\tBB\tAB\tstrength\n"
            f"{AA:.6f}\t{BB:.6f}\t{AB:.6f}\t{strength:.6f}\n"
        )
        logger.info("compartment strength = (%.3f×%.3f)/%.3f² = %.4f", AA, BB, AB, strength)
        return out_tsv, {"AA": AA, "BB": BB, "AB": AB, "strength": strength}
    except Exception as exc:  # noqa: BLE001
        logger.warning("compartment-strength computation failed (%s).", exc)
        return None, None


def _load_strength(strength_tsv: Path, res: "CompartmentResult") -> None:
    try:
        import pandas as pd
        row = pd.read_csv(strength_tsv, sep="\t").iloc[0]
        res.aa, res.bb, res.ab, res.strength = (
            float(row["AA"]), float(row["BB"]), float(row["AB"]), float(row["strength"]))
        res.strength_tsv = strength_tsv
    except Exception:  # noqa: BLE001
        pass


def _saddle_curve(m):
    """(AA+BB)/(AB+BA) accumulated from the corners over extents 1..n/2."""
    import numpy as np
    n = m.shape[0]
    xs, ys = [], []
    for k in range(1, n // 2 + 1):
        AA = np.nanmean(m[-k:, -k:]); BB = np.nanmean(m[:k, :k])
        AB = np.nanmean(m[-k:, :k]); BA = np.nanmean(m[:k, -k:])
        denom = AB + BA
        xs.append(k); ys.append((AA + BB) / denom if denom else float("nan"))
    return xs, ys


def _plot_saddle(npz_path, out_dir, sample_name, resolution, strength=None):
    """Render the saddle obs/exp heatmap (square, log diverging about 1)."""
    try:
        import numpy as np
        import matplotlib.pyplot as plt
        from matplotlib.colors import LogNorm
        viz.setup_plot_style()
        d = np.load(npz_path, allow_pickle=True)
        if "saddledata" not in d.files:
            return None
        m = np.asarray(d["saddledata"], dtype=float)[1:-1, 1:-1]  # drop flanking bins
        finite = m[np.isfinite(m) & (m > 0)]
        if m.ndim != 2 or finite.size == 0:
            return None
        hi = float(np.nanpercentile(finite, 98)); lo = float(np.nanpercentile(finite, 2))
        r = max(hi, 1.0 / lo if lo > 0 else hi, 1.3)
        fig, ax = plt.subplots(figsize=(4.6, 4))
        im = ax.imshow(m, cmap="coolwarm", norm=LogNorm(vmin=1.0 / r, vmax=r), origin="lower")
        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label("observed / expected")
        ax.set_xlabel("E1 quantile  (B \u2192 A)")
        ax.set_ylabel("E1 quantile  (B \u2192 A)")
        ax.set_xticks([]); ax.set_yticks([])
        title = f"{sample_name}  saddle @ {resolution // 1000} kb"
        if strength is not None:
            title += f"\nstrength = {strength:.2f}"
        ax.set_title(title)
        return viz.save_figure(fig, f"{sample_name}.saddle.{resolution}", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("saddle heatmap failed (%s).", exc)
        return None


def plot_saddle_strength_all(results, out_dir, sample_sheet=None):
    """≥2-sample overlay: (AA+BB)/(AB+BA) vs extent + a strength bar."""
    try:
        import numpy as np
        import matplotlib.pyplot as plt
        viz.setup_plot_style()
        series = []
        for r in results:
            if not getattr(r, "saddle_npz", None):
                continue
            d = np.load(r.saddle_npz, allow_pickle=True)
            if "saddledata" not in d.files:
                continue
            m = np.asarray(d["saddledata"], dtype=float)[1:-1, 1:-1]
            xs, ys = _saddle_curve(m)
            series.append((r.sample_name, xs, ys, getattr(r, "strength", None)))
        if len(series) < 2:
            return None
        colors = viz.sample_colors([s[0] for s in series])
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4), gridspec_kw={"width_ratios": [1.5, 1]})
        for name, xs, ys, _ in series:
            ax1.step(xs, ys, where="mid", color=colors[name], lw=2, label=name)
        ax1.set_xlabel("Extent (quantile bins from corner)")
        ax1.set_ylabel("(AA + BB) / (AB + BA)")
        ax1.set_title("Compartment strength vs extent")
        ax1.legend()
        names = [s[0] for s in series]
        strengths = [s[3] if s[3] is not None else np.nan for s in series]
        ax2.bar(range(len(names)), strengths, color=[colors[n] for n in names])
        ax2.set_xticks(range(len(names)))
        ax2.set_xticklabels(names, rotation=45, ha="right")
        ax2.set_ylabel("strength  (AA\u00b7BB)/AB\u00b2")
        ax2.set_title("Compartment strength")
        return viz.save_figure(fig, "saddle_strength_all", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("saddle_strength_all failed (%s).", exc)
        return None



def _quantile_normalize(arr):
    """Quantile-normalize the COLUMNS of a (features x samples) array.

    Forces every sample (column) to share one distribution (the mean of the
    per-rank sorted values), so compartment scores are comparable across
    samples before PCA. Bolstad et al., Bioinformatics 2003
    (doi:10.1093/bioinformatics/19.2.185).
    """
    import numpy as np
    a = np.asarray(arr, dtype=float)
    ranks = np.argsort(np.argsort(a, axis=0), axis=0)
    mean_sorted = np.sort(a, axis=0).mean(axis=1)
    return mean_sorted[ranks]


def _plot_compartment_pca(scores, var, names, out_dir, sample_sheet, resolution, n_bins):
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
        ax.set_title(f"Compartment PCA (E1 @ {res_lab}, {n_bins} bins)")
        ax.legend()
        return viz.save_figure(fig, "compartment_pca", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("compartment PCA plot failed (%s).", exc)
        return None


def run_compartment_pca(results, out_dir, *, resolution, sample_sheet=None):
    """Sample PCA on GC-phased compartment eigenvectors (E1), dcHiC-style.

    Builds a (bins x samples) matrix of the GC-phased E1 compartment score
    (cooltools eigs-cis), quantile-normalizes across samples, then PCA (numpy
    SVD) across samples -> a PC1/PC2 scatter coloured by condition. Asks whether
    samples separate by their genome-wide compartment profile; complements the
    saddle-strength readout.

    Sources / method:
      * A/B compartments are PC1 of the Hi-C observed/expected correlation
        matrix - Lieberman-Aiden et al., Science 2009 (doi:10.1126/science.1181369).
      * Cross-sample comparison by PCA on QUANTILE-NORMALIZED compartment (PC1)
        scores follows dcHiC - Chakraborty, Wang & Ay, Nat Commun 2022
        (doi:10.1038/s41467-022-34626-6); dcHiC PCA-projects + quantile-normalizes
        compartment scores across datasets, then scores per-bin differential
        compartments via Mahalanobis distance (a richer step we do not replicate).
      * Quantile normalization - Bolstad et al., Bioinformatics 2003
        (doi:10.1093/bioinformatics/19.2.185).
    E1 signs are already GC-phased (A = +), so scores are directly comparable
    across samples without re-orientation.
    """
    try:
        import numpy as np
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        logger.warning("numpy/pandas unavailable (%s) — no compartment PCA.", exc)
        return None
    if len(results) < 3:
        logger.info("compartment PCA skipped (need >=3 samples for a 2D embedding).")
        return None
    try:
        cols = {}
        for r in results:
            ev = getattr(r, "eigs_vecs", None)
            if not ev or not Path(ev).exists():
                continue
            df = pd.read_csv(ev, sep="\t")
            e1 = "E1" if "E1" in df.columns else next(
                (c for c in df.columns if c.upper().startswith("E1")), None)
            if e1 is None or not {"chrom", "start"} <= set(df.columns):
                continue
            key = df["chrom"].astype(str) + ":" + df["start"].astype(str)
            cols[r.sample_name] = pd.Series(df[e1].values, index=key)
        if len(cols) < 3:
            return None
        mat = pd.DataFrame(cols).dropna()          # bins x samples, common non-NaN bins
        if mat.shape[0] < 2:
            return None
        names = list(mat.columns)
        Xn = _quantile_normalize(mat.values)       # QN across samples
        Xc = Xn.T - Xn.T.mean(axis=0, keepdims=True)
        U, S, _ = np.linalg.svd(Xc, full_matrices=False)
        scores = U * S
        var = (S ** 2) / np.sum(S ** 2) if np.sum(S ** 2) > 0 else np.zeros_like(S)
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        ncomp = min(scores.shape[1], 5)
        pd.DataFrame(scores[:, :ncomp], index=names,
                     columns=[f"PC{i + 1}" for i in range(ncomp)]).to_csv(
            out_dir / "compartment_pca_coords.tsv", sep="\t")
        png = _plot_compartment_pca(scores, var, names, out_dir, sample_sheet, resolution, mat.shape[0])
        return {"png": str(png) if png else None,
                "coords": str(out_dir / "compartment_pca_coords.tsv"),
                "var": [float(v) for v in var[:2]], "n_bins": int(mat.shape[0])}
    except Exception as exc:  # noqa: BLE001
        logger.warning("compartment PCA failed (%s).", exc)
        return None


def run_compartments(
    sample_name: str,
    mcool: Path,
    resolution: int,
    fasta: Path,
    comp_dir: Path,
    saddle_dir: Path,
    *,
    n_eigs: int = 1,
    phasing_track: Path | None = None,
    nproc: int = 8,
    is_combined: bool = False,
) -> CompartmentResult:
    """Compartments for one sample at one resolution.

    Compartment-track files (view / expected-cis / GC / eigs / A/B BED) are
    written under ``comp_dir``; saddle products (saddledump.npz, digitized.tsv,
    strength.tsv, heatmap png/pdf) under ``saddle_dir``.
    """
    comp_dir = Path(comp_dir); comp_dir.mkdir(parents=True, exist_ok=True)
    saddle_dir = Path(saddle_dir); saddle_dir.mkdir(parents=True, exist_ok=True)
    uri = f"{mcool}::resolutions/{resolution}"
    res = CompartmentResult(sample_name=sample_name, resolution=resolution, is_combined=is_combined)

    _prefix = comp_dir / f"{sample_name}.eigs.{resolution}"
    _vecs = Path(f"{_prefix}.cis.vecs.tsv")
    _lam  = Path(f"{_prefix}.cis.lam.txt")
    _exp  = comp_dir / f"{sample_name}.expected_cis.{resolution}.tsv"
    _gc   = comp_dir / f"gc.{resolution}.tsv"            # shared across samples (genome GC)
    _ab   = comp_dir / f"{sample_name}.AB.{resolution}.bed"
    _view = comp_dir / f"view.{resolution}.bed"          # shared across samples (main chroms)
    _sprefix = saddle_dir / f"{sample_name}.saddle.{resolution}"
    _snpz = Path(f"{_sprefix}.saddledump.npz")
    _spng = saddle_dir / f"{sample_name}.saddle.{resolution}.png"
    _str  = saddle_dir / f"{sample_name}.strength.{resolution}.tsv"

    # Checkpoint: reuse a completed eigenvector (delete the .eigs.* files to re-run).
    if _vecs.exists() and _vecs.stat().st_size > 0:
        logger.info("  [%s] checkpoint: eigenvector exists — skipping cooltools", sample_name)
        res.eigs_vecs = _vecs
        res.eigs_lam = _lam if _lam.exists() else None
        res.expected_tsv = _exp if _exp.exists() else None
        res.gc_track = _gc if _gc.exists() else None
        res.view_bed = _view if _view.exists() else None
        res.ab_bed = _ab if _ab.exists() else _ab_bed_from_vecs(_vecs, _ab)
        res.saddle_npz = _snpz if _snpz.exists() else None
        if _str.exists():
            _load_strength(_str, res)
        elif res.saddle_npz:
            res.strength_tsv, sv = _compartment_strength(res.saddle_npz, _str)
            if sv:
                res.aa, res.bb, res.ab, res.strength = sv["AA"], sv["BB"], sv["AB"], sv["strength"]
        if res.saddle_npz:
            res.saddle_png = _spng if _spng.exists() else _plot_saddle(
                res.saddle_npz, saddle_dir, sample_name, resolution, res.strength)
        return res

    if not check("cooltools"):
        logger.warning("cooltools not found — skipping compartments.")
        return res

    # 0. main-chromosome view (drop scaffolds smaller than a few bins / 1 Mb).
    res.view_bed = _view if _view.exists() else _make_chrom_view(
        uri, _view, min_size=max(10 * resolution, 1_000_000))
    view_opt = ["--view", str(res.view_bed)] if res.view_bed else []

    # 1. expected-cis (needed for saddle) — same view as eigs/saddle.
    res.expected_tsv = _exp
    try:
        run(["cooltools", "expected-cis", "-p", nproc, *view_opt, "-o", res.expected_tsv, uri],
            label=f"expected-cis [{resolution}]")
    except RuntimeError as exc:
        logger.warning("expected-cis failed (%s).", exc)
        res.expected_tsv = None

    # 2. phasing track (user-supplied or GC) + eigs-cis.
    if phasing_track and Path(phasing_track).exists():
        res.gc_track = Path(phasing_track)
    elif _gc.exists():
        res.gc_track = _gc                                   # reuse shared GC track
    else:
        res.gc_track = make_gc_track(uri, fasta, _gc, view_bed=res.view_bed)
    cmd = ["cooltools", "eigs-cis", "--n-eigs", n_eigs, *view_opt, "-o", _prefix]
    if res.gc_track:
        cmd += ["--phasing-track", res.gc_track]
    cmd += [uri]
    try:
        run(cmd, label=f"eigs-cis [{resolution}]")
        res.eigs_vecs = _vecs if _vecs.exists() else None
        res.eigs_lam  = _lam if _lam.exists() else None
        if res.eigs_vecs:
            res.ab_bed = _ab_bed_from_vecs(res.eigs_vecs, _ab)
    except RuntimeError as exc:
        logger.warning("eigs-cis failed (%s) — no compartment track.", exc)
        return res

    # 3. saddle (compartment strength) — needs vecs + expected.
    if res.eigs_vecs and res.expected_tsv:
        try:
            run(["cooltools", "saddle", "--qrange", "0.025", "0.975", "--n-bins", "38",
                 *view_opt, "-o", _sprefix, uri,
                 f"{res.eigs_vecs}::E1", res.expected_tsv],
                label=f"saddle [{resolution}]")
            res.saddle_npz = _snpz if _snpz.exists() else None
        except RuntimeError as exc:
            logger.warning("saddle failed (%s).", exc)

    # 4. compartment-strength scalar from the saddle quantile matrix.
    if res.saddle_npz:
        res.strength_tsv, sv = _compartment_strength(res.saddle_npz, _str)
        if sv:
            res.aa, res.bb, res.ab, res.strength = sv["AA"], sv["BB"], sv["AB"], sv["strength"]
        res.saddle_png = _plot_saddle(res.saddle_npz, saddle_dir, sample_name, resolution, res.strength)
    return res
