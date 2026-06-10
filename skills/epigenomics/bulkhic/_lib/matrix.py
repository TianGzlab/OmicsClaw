"""
matrix.py — Bulk Hi-C Step 3: ``.pairs`` → balanced ``.cool`` / ``.mcool``.

    cooler cload pairs -c1 2 -p1 3 -c2 4 -p2 5 --assembly <genome>
        <chrom.sizes>:<base_binsize> <pairs.gz> <sample>.<base>.cool
    cooler balance --mad-max 5 <sample>.<base>.cool
    cooler zoomify --balance -r <resolutions> -o <sample>.mcool <sample>.<base>.cool

Then the foundational matrix QC — contact-distance decay **P(s)** via
``cooltools expected-cis`` (+ a log-log plot) — and, when ecosystem=Both and a
``juicer_tools`` jar is available, a best-effort ``.hic`` export for Juicebox
(graceful skip otherwise; no GPU / HiCCUPS involved).

The ``.pairs`` column layout is the pairtools default: ``readID, chrom1, pos1,
chrom2, pos2, strand1, strand2, …`` → cooler columns ``-c1 2 -p1 3 -c2 4 -p2 5``
(1-based), strands at columns 6/7.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)

# Default multi-resolution pyramid (all multiples of the base binsize).
DEFAULT_BASE_BINSIZE = 1_000
DEFAULT_RESOLUTIONS = [1_000, 2_000, 5_000, 10_000, 25_000, 50_000,
                       100_000, 250_000, 500_000, 1_000_000]
# Resolution used for the P(s) decay QC plot (fine enough to show the slope).
DEFAULT_PS_RESOLUTION = 10_000


@dataclass
class MatrixResult:
    sample_name:   str
    cool:          Path
    mcool:         Path
    base_binsize:  int
    resolutions:   list[int] = field(default_factory=list)
    balanced:      bool = True
    hic:           Path | None = None
    expected_tsv:  Path | None = None
    ps_png:        Path | None = None
    # Per-condition replicate pool (see run_combined_matrices). For ordinary
    # single-sample matrices these stay at their defaults.
    is_combined:   bool = False
    condition:     str | None = None
    members:       list[str] = field(default_factory=list)


# ===========================================================================
# Matrix construction
# ===========================================================================

def cload_pairs(pairs: Path, chrom_sizes: Path, base_binsize: int, out_cool: Path,
                *, genome: str, nproc: int = 8) -> Path:
    out_cool.parent.mkdir(parents=True, exist_ok=True)
    if out_cool.exists():
        logger.info("  base cool exists — skipping cload: %s", out_cool)
        return out_cool
    _require("cooler")
    _run(
        ["cooler", "cload", "pairs", "-c1", "2", "-p1", "3", "-c2", "4", "-p2", "5",
         "--assembly", genome, f"{chrom_sizes}:{base_binsize}", str(pairs), str(out_cool)],
        label=f"cooler cload pairs [{out_cool.name}]",
    )
    return out_cool


def cooler_merge(out_cool: Path, member_cools: list[Path]) -> Path:
    """Pool replicate base ``.cool`` files into one (raw contact counts summed).

    ``cooler merge`` requires every input to share the same bin table, which the
    per-replicate base cools do — they were all cload'ed at the same base binsize
    against the same chrom.sizes. The merged cool is unbalanced; the caller
    balances + zoomifies it just like a single-sample matrix.
    """
    out_cool.parent.mkdir(parents=True, exist_ok=True)
    if out_cool.exists():
        logger.info("  merged cool exists — skipping merge: %s", out_cool)
        return out_cool
    _require("cooler")
    _run(["cooler", "merge", str(out_cool), *[str(c) for c in member_cools]],
         label=f"cooler merge [{out_cool.name}] ({len(member_cools)} reps)")
    return out_cool


def balance_cool(cool: Path, *, nproc: int = 8, mad_max: int = 5) -> None:
    _run(["cooler", "balance", "--force", "--nproc", str(nproc), "--mad-max", str(mad_max), str(cool)],
         label=f"cooler balance [{cool.name}]")


def zoomify(cool: Path, resolutions: list[int], out_mcool: Path, *, nproc: int = 8) -> Path:
    if out_mcool.exists():
        logger.info("  mcool exists — skipping zoomify: %s", out_mcool)
        return out_mcool
    res_csv = ",".join(str(r) for r in resolutions)
    _run(["cooler", "zoomify", "--balance", "--nproc", str(nproc),
          "-r", res_csv, "-o", str(out_mcool), str(cool)],
         label=f"cooler zoomify [{out_mcool.name}]")
    return out_mcool


def compute_expected_ps(
    mcool: Path, resolution: int, out_tsv: Path, out_png: Path, *, nproc: int = 8,
) -> tuple[Path | None, Path | None]:
    """cooltools.expected_cis (smoothed) → P(s) table + P(s)/slope plot (graceful).

    Mirrors production 1_draw_contact_distance.py: smooth=True, smooth_sigma=0.1,
    aggregate_smoothed=True on the ICE-balanced ('weight') matrix, restricted to a
    main-chromosome view (drops tiny scaffolds). Falls back gracefully.
    """
    try:
        import cooler
        import cooltools
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        logger.warning("cooler/cooltools unavailable (%s) — skipping P(s) QC.", exc)
        return None, None
    cooler_uri = f"{mcool}::resolutions/{resolution}"
    try:
        clr = cooler.Cooler(cooler_uri)
        sizes = clr.chromsizes
        keep = sizes[sizes >= 1_000_000]
        view_df = None
        if not keep.empty:
            view_df = pd.DataFrame({"chrom": keep.index, "start": 0,
                                    "end": keep.values, "name": keep.index})
        cvd = cooltools.expected_cis(
            clr=clr, view_df=view_df, smooth=True, smooth_sigma=0.1,
            aggregate_smoothed=True, clr_weight_name="weight", nproc=nproc,
        )
        cvd.to_csv(out_tsv, sep="\t", index=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("expected_cis failed (%s) — skipping P(s) QC.", exc)
        return None, None
    png = _plot_ps(out_tsv, out_png, resolution)
    return out_tsv, png


def _read_ps(expected_tsv, resolution):
    """Return (x_bp, P(s), log-log slope) from a cooltools expected-cis table."""
    import numpy as np
    import pandas as pd
    df = pd.read_csv(expected_tsv, sep="\t")
    col = next((c for c in ("balanced.avg.smoothed.agg", "balanced.avg.smoothed",
                            "balanced.avg", "count.avg") if c in df.columns), None)
    if col is None or "dist" not in df.columns:
        return None
    g = df.groupby("dist")
    agg = g[col].mean().reset_index()
    agg.loc[agg["dist"] < 2, col] = np.nan
    if "n_valid" in df.columns:
        nv = g["n_valid"].sum().reindex(agg["dist"]).to_numpy(dtype=float)
        thr = max(10.0, 0.005 * np.nanmax(nv))
        agg.loc[nv < thr, col] = np.nan   # drop the ultra-sparse tail (noisy slope)
    agg = agg[agg["dist"] > 0]
    x = agg["dist"].to_numpy(dtype=float) * resolution
    y = agg[col].to_numpy(dtype=float)
    m = np.isfinite(y) & (y > 0)
    x, y = x[m], y[m]
    if x.size < 3:
        return None
    slope = np.gradient(np.log(y), np.log(x))
    return x, y, slope


def _plot_ps(expected_tsv: Path, out_png: Path, resolution: int) -> Path | None:
    try:
        import matplotlib.pyplot as plt
        from . import viz
        viz.setup_plot_style()
    except Exception as exc:  # noqa: BLE001
        logger.warning("matplotlib unavailable (%s) — no P(s) plot.", exc)
        return None
    r = _read_ps(expected_tsv, resolution)
    if r is None:
        logger.warning("could not read P(s) from %s.", expected_tsv)
        return None
    x, y, slope = r
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(5, 6),
                                   gridspec_kw={"height_ratios": [2, 1]}, sharex=True)
    ax1.loglog(x, y, color=viz.PALETTE[0], lw=2)
    ax1.set_ylabel("IC contact frequency  P(s)")
    ax1.set_title(f"Contact-distance decay  @ {resolution:,} bp")
    ax2.semilogx(x, slope, color=viz.PALETTE[0], lw=2)
    ax2.axhline(-1.0, ls=":", color="grey", lw=1)
    ax2.set_xlabel("Separation (bp)")
    ax2.set_ylabel("Slope")
    ax2.set_ylim(-2.5, 0.5)
    return viz.save_figure(fig, Path(out_png).stem, Path(out_png).parent)


def plot_pofs_all(results, out_dir, resolution):
    """≥2-sample overlay of P(s) decay + log-log slope (the MS contact-distance figure)."""
    try:
        import matplotlib.pyplot as plt
        from . import viz
        viz.setup_plot_style()
        series = []
        for r in results:
            et = getattr(r, "expected_tsv", None)
            if not et or not Path(et).exists():
                continue
            d = _read_ps(et, resolution)
            if d:
                series.append((r.sample_name, d[0], d[1], d[2]))
        if len(series) < 2:
            return None
        colors = viz.sample_colors([s[0] for s in series])
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(5.5, 6.5),
                                       gridspec_kw={"height_ratios": [2, 1]}, sharex=True)
        for name, x, y, slope in series:
            ax1.loglog(x, y, color=colors[name], lw=1.0, label=name)
            ax2.semilogx(x, slope, color=colors[name], lw=1.0)
        ax1.set_ylabel("IC contact frequency")
        ax1.set_title("Contact-distance decay  P(s)")
        ax1.legend()
        ax2.axhline(-1.0, ls=":", color="grey", lw=1)
        ax2.set_xlabel("Separation (bp)")
        ax2.set_ylabel("Slope")
        ax2.set_ylim(-2.5, 0.5)
        return viz.save_figure(fig, "P_curve_of_all", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("P_curve_of_all failed (%s).", exc)
        return None


def _parse_scc(path):
    """Mean SCC across chromosomes from a hicrep output file (skips '#' header lines)."""
    import numpy as np
    vals = []
    try:
        for ln in open(path):
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            try:
                vals.append(float(ln.split()[0]))
            except ValueError:
                pass
    except OSError:
        return float("nan")
    return float(np.nanmean(vals)) if vals else float("nan")


def _plot_scc_heatmap(mat, out_dir):
    """Clustered SCC heatmap (seaborn clustermap; falls back to a plain heatmap)."""
    try:
        import numpy as np
        import matplotlib.pyplot as plt
        import seaborn as sns
        from . import viz
        viz.setup_plot_style()
        off = mat.values[np.triu_indices_from(mat.values, 1)]
        finite = off[np.isfinite(off)]
        vmin = float(np.nanmin(finite)) if finite.size else 0.9
        vmin = min(vmin, 0.95)
        try:
            g = sns.clustermap(mat, cmap="viridis", vmin=vmin, vmax=1.0, annot=True,
                               fmt=".3f", annot_kws={"size": 8}, figsize=(5.6, 5.6),
                               cbar_kws={"ticks": [vmin, (vmin + 1) / 2, 1.0]})
            g.fig.suptitle("Replicate reproducibility (HiCRep SCC)", y=1.02)
            fig = g.fig
        except Exception:  # noqa: BLE001 — clustering can fail (NaNs / tiny N)
            fig, ax = plt.subplots(figsize=(5.6, 5))
            sns.heatmap(mat, cmap="viridis", vmin=vmin, vmax=1.0, annot=True, fmt=".3f",
                        annot_kws={"size": 8}, square=True, ax=ax)
            ax.set_title("Replicate reproducibility (HiCRep SCC)")
        return viz.save_figure(fig, "scc_heatmap", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SCC heatmap failed (%s).", exc)
        return None


def run_scc_reproducibility(mcools, output_dir, *, resolution=10000, h=None, dBPMax=500000):
    """Pairwise HiCRep SCC across replicate .mcools + a clustered heatmap.

    `mcools` is a list of (sample_name, mcool_path) — the per-replicate matrices.
    Mirrors the production 0_data_quality SCC QC (h=20, dBPMax=500kb @ 10 kb).

    Source: HiCRep stratum-adjusted correlation coefficient (Yang et al., Genome
    Res 2017); CLI from HiCRep.py (Lin et al., Bioinformatics 2021).
    """
    import itertools
    import shutil
    import subprocess
    import numpy as np
    import pandas as pd
    if h is None:
        h = max(1, round(200000 / resolution))  # ~200 kb smoothing window (hicrep docs)
    if len(mcools) < 2:
        return None
    if not shutil.which("hicrep"):
        logger.warning("hicrep not found — skipping SCC reproducibility. Run 0_setup_env_for_bulkhic.sh.")
        return None
    # main chromosomes (>=1 Mb) — drop tiny scaffolds hicrep can't handle
    try:
        import cooler
        sizes = cooler.Cooler(f"{mcools[0][1]}::resolutions/{resolution}").chromsizes
        chroms = [c for c, l in sizes.items() if l >= 1_000_000]
    except Exception as exc:  # noqa: BLE001
        logger.warning("SCC: could not resolve chromosomes (%s).", exc)
        chroms = []
    names = [s for s, _ in mcools]
    mat = pd.DataFrame(1.0, index=names, columns=names)
    output_dir.mkdir(parents=True, exist_ok=True)
    sccdir = output_dir / "pairs"
    sccdir.mkdir(parents=True, exist_ok=True)
    for (s1, m1), (s2, m2) in itertools.combinations(mcools, 2):
        out = sccdir / f"scc_{s1}_vs_{s2}.txt"
        cmd = ["hicrep", str(m1), str(m2), str(out),
               "--binSize", str(resolution), "--h", str(h), "--dBPMax", str(dBPMax)]
        if chroms:
            cmd += ["--chrNames", *chroms]
        logger.info("Running: hicrep [%s vs %s]", s1, s2)
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            scc = _parse_scc(out)
        except Exception as exc:  # noqa: BLE001
            logger.warning("hicrep %s vs %s failed (%s).", s1, s2, exc)
            scc = float("nan")
        mat.loc[s1, s2] = scc
        mat.loc[s2, s1] = scc
    tsv = output_dir / "scc_values.tsv"
    mat.to_csv(tsv, sep="\t")
    png = _plot_scc_heatmap(mat, output_dir)
    off = mat.values[np.triu_indices_from(mat.values, 1)]
    finite = off[np.isfinite(off)]
    return {"tsv": tsv, "png": png,
            "min_scc": float(np.nanmin(finite)) if finite.size else None,
            "mean_scc": float(np.nanmean(finite)) if finite.size else None}


def _pca_features(mcool_uri, chroms, band_bins):
    """Flatten a sample's balanced cis contacts (upper band) -> {(chrom,i,j): value}."""
    import numpy as np
    import cooler
    from scipy import sparse
    clr = cooler.Cooler(mcool_uri)
    feats = {}
    for ch in chroms:
        try:
            m = sparse.triu(clr.matrix(balance=True, sparse=True).fetch(ch), k=1).tocoo()
        except Exception:  # noqa: BLE001
            continue
        for i, j, v in zip(m.row, m.col, m.data):
            d = int(j) - int(i)
            if 1 <= d <= band_bins and np.isfinite(v):
                feats[(ch, int(i), int(j))] = float(v)
    return feats


def _plot_pca(scores, var, names, out_dir, sample_sheet=None):
    try:
        import numpy as np
        import matplotlib.pyplot as plt
        from . import viz
        viz.setup_plot_style()
        conds = [viz.condition_of(n, sample_sheet) for n in names]
        ucond = list(dict.fromkeys(conds))
        ccolor = {c: viz.PALETTE[i % len(viz.PALETTE)] for i, c in enumerate(ucond)}
        pc1 = scores[:, 0]
        pc2 = scores[:, 1] if scores.shape[1] > 1 else np.zeros_like(pc1)
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
        ax.set_title("Replicate PCA (contact matrices)")
        ax.legend()
        return viz.save_figure(fig, "sample_pca", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PCA plot failed (%s).", exc)
        return None


def run_pca_reproducibility(mcools, out_dir, *, resolution, dBPMax=500000, sample_sheet=None):
    """Sample PCA on flattened balanced cis contacts (scHiCluster-style embedding).

    Each sample -> a feature vector of its balanced cis contacts within `dBPMax`
    over main chromosomes; PCA (numpy SVD) across samples -> a PC1/PC2 scatter
    coloured by condition. Complements the HiCRep SCC heatmap.

    Source / method: PCA on the contact matrices for Hi-C sample clustering follows
    the scHiCluster embedding (Zhou et al., PNAS 2019, doi:10.1073/pnas.1901423116 —
    contact vectors are PCA-transformed, then embedded). The complementary SCC view
    (the heatmap) uses HiCRep (Yang et al., Genome Res 2017; HiCRep.py, Lin et al.,
    Bioinformatics 2021), which documents SCC-as-distance sample embeddings.
    """
    import numpy as np
    if len(mcools) < 3:
        logger.info("PCA skipped (need >=3 samples for a 2D embedding).")
        return None
    try:
        import cooler
        sizes = cooler.Cooler(f"{mcools[0][1]}::resolutions/{resolution}").chromsizes
        chroms = [c for c, l in sizes.items() if l >= 1_000_000]
    except Exception as exc:  # noqa: BLE001
        logger.warning("PCA: could not resolve chromosomes (%s).", exc)
        return None
    band = max(1, dBPMax // resolution)
    per = [(name, _pca_features(f"{m}::resolutions/{resolution}", chroms, band)) for name, m in mcools]
    keys = sorted(set().union(*[set(d) for _, d in per])) if per else []
    if len(keys) < 2:
        return None
    X = np.log1p(np.array([[d.get(k, 0.0) for k in keys] for _, d in per], dtype=float))
    Xc = X - X.mean(axis=0, keepdims=True)
    U, S, _ = np.linalg.svd(Xc, full_matrices=False)
    scores = U * S
    var = (S ** 2) / np.sum(S ** 2) if np.sum(S ** 2) > 0 else np.zeros_like(S)
    names = [n for n, _ in per]
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    ncomp = min(scores.shape[1], 5)
    pd.DataFrame(scores[:, :ncomp], index=names,
                 columns=[f"PC{i + 1}" for i in range(ncomp)]).to_csv(out_dir / "pca_coords.tsv", sep="\t")
    png = _plot_pca(scores, var, names, out_dir, sample_sheet)
    return {"png": str(png) if png else None, "coords": str(out_dir / "pca_coords.tsv"),
            "var": [float(v) for v in var[:2]]}


def _mcool_resolutions(mcool) -> list[int]:
    """Sorted list of integer resolutions stored in an .mcool."""
    try:
        import cooler
        return sorted(int(u.rsplit("/", 1)[-1])
                      for u in cooler.fileops.list_coolers(str(mcool)))
    except Exception:  # noqa: BLE001
        return []


def _whitered_cmap():
    """HapHiC/GenAsmClaw-style white->red->dark colormap (masked bins white)."""
    import matplotlib.colors as mcolors
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "white_red", ["#FFFFFF", "#FFF5F0", "#FB6A4A", "#CB181D", "#67000D"])
    cmap.set_bad("#FFFFFF")
    return cmap


def plot_contact_map(mcool, resolution, out_dir, sample_name, *, sample_sheet=None):
    """Whole-genome balanced Hi-C contact map (GenAsmClaw/HapHiC drawing style).

    Loads the genome-wide ICE-balanced matrix at `resolution`, draws it with a
    white->red colormap on a log color scale, overlays chromosome-boundary
    gridlines, and labels each chromosome at its bin-block centre. Mirrors the
    HapHiC ``HapHiC_plot`` contact-map style used in GenAsmClaw
    (``utils/hic_hifi_dotplot.py``): per-chromosome bin blocks, boundary
    separators, white->red ramp.
    """
    try:
        import numpy as np
        import cooler
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        from . import viz
        viz.setup_plot_style()
        clr = cooler.Cooler(f"{mcool}::resolutions/{resolution}")
        # Restrict to main chromosomes (drop unplaced/alt scaffolds + tiny contigs).
        sizes = clr.chromsizes
        min_size = max(int(resolution) * 4, 1_000_000)
        chroms = [c for c in clr.chromnames if int(sizes[c]) >= min_size]
        if not chroms:
            chroms = list(clr.chromnames)
        spans = [clr.extent(c) for c in chroms]           # (lo, hi) bin range per chrom
        idx = np.concatenate([np.arange(lo, hi) for lo, hi in spans])
        try:
            full = np.asarray(clr.matrix(balance=True)[:], dtype=float)
        except Exception:  # noqa: BLE001 — unbalanced fallback
            full = np.asarray(clr.matrix(balance=False)[:], dtype=float)
        mat = full[np.ix_(idx, idx)]
        lens = [hi - lo for lo, hi in spans]
        edges = [0, *list(np.cumsum(lens))]
        centers = [(edges[i] + edges[i + 1]) / 2.0 for i in range(len(chroms))]
        vals = mat[np.isfinite(mat) & (mat > 0)]
        if vals.size == 0:
            logger.warning("contact map: empty matrix for %s.", sample_name)
            return None
        vmax = float(np.percentile(vals, 99))
        vmin = max(float(np.percentile(vals, 20)), vmax / 1e3)
        norm = mcolors.LogNorm(vmin=vmin, vmax=vmax)
        cmap = _whitered_cmap(); cmap.set_under("#FFFFFF"); cmap.set_bad("#FFFFFF")
        mp = np.ma.masked_invalid(mat)
        n = mat.shape[0]
        res_lab = f"{resolution // 1000} kb" if resolution % 1000 == 0 else f"{resolution} bp"
        fig, ax = plt.subplots(figsize=(6.4, 5.6))
        ax.set_facecolor("#FFFFFF")
        im = ax.imshow(mp, cmap=cmap, norm=norm,
                       interpolation="none", origin="upper", aspect="equal")
        for e in edges[1:-1]:
            ax.axhline(e - 0.5, color="0.4", lw=0.5)
            ax.axvline(e - 0.5, color="0.4", lw=0.5)
        ax.set_xlim(-0.5, n - 0.5)
        ax.set_ylim(n - 0.5, -0.5)
        ax.set_xticks(centers); ax.set_xticklabels(chroms, rotation=90, fontsize=8)
        ax.set_yticks(centers); ax.set_yticklabels(chroms, fontsize=8)
        ax.tick_params(length=0)
        ax.set_title(f"{sample_name}  whole-genome contact map @ {res_lab}")
        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
        cb.set_label("balanced contacts (log)")
        return viz.save_figure(fig, sample_name, out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("plot_contact_map(%s) failed (%s).", sample_name, exc)
        return None


def run_all_contact_maps(results, out_dir, *, resolution=500000, sample_sheet=None):
    """Per-sample whole-genome contact maps into ``out_dir`` (one png/pdf each)."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    made = {}
    for r in results:
        avail = _mcool_resolutions(r.mcool)
        res = resolution if resolution in avail else (max(avail) if avail else resolution)
        png = plot_contact_map(r.mcool, res, out_dir, r.sample_name, sample_sheet=sample_sheet)
        if png:
            made[r.sample_name] = str(png)
    return made


def export_hic(pairs: Path | list[Path], chrom_sizes: Path, out_hic: Path, *,
               juicer_jar: Path | None) -> Path | None:
    """Best-effort .hic export via juicer_tools pre (graceful skip).

    Converts the .pairs to juicer 'short' format (strand chr pos frag) and runs
    ``java -jar juicer_tools pre``. Requires Java + the jar; any failure logs a
    warning and returns None — the cooler/.mcool path is unaffected.

    ``pairs`` may be a single path or a list (pooled replicates): ``zcat`` reads
    all of them and the per-line ``#``-header skip keeps each file's header out
    of the stream, so the short-format records simply concatenate.
    """
    if juicer_jar is None or not Path(juicer_jar).exists():
        logger.warning(".hic export skipped — no juicer_tools jar (set --juicer-jar).")
        return None
    if not shutil.which("java"):
        logger.warning(".hic export skipped — Java not found.")
        return None
    pairs_list = [pairs] if isinstance(pairs, (str, Path)) else list(pairs)
    pairs_arg = " ".join(str(p) for p in pairs_list)
    short = out_hic.with_suffix(".short.txt")
    try:
        # pairs cols: 1 readID, 2 chr1, 3 pos1, 4 chr2, 5 pos2, 6 strand1, 7 strand2
        awk = (
            r"""zcat -f %s | awk 'BEGIN{OFS=" "} /^#/{next} """
            r"""{s1=($6=="-")?16:0; s2=($7=="-")?16:0; print s1,$2,$3,0,s2,$4,$5,1}' > %s"""
        ) % (pairs_arg, short)
        _run_shell(awk, label=f"pairs→juicer-short [{out_hic.name}]")
        _run_shell(
            f"java -Xmx8g -jar {juicer_jar} pre -r "
            f"{','.join(str(r) for r in DEFAULT_RESOLUTIONS)} {short} {out_hic} {chrom_sizes}",
            label=f"juicer_tools pre [{out_hic.name}]",
        )
        short.unlink(missing_ok=True)
        return out_hic if out_hic.exists() else None
    except RuntimeError as exc:
        logger.warning(".hic export failed (%s) — continuing with cooler outputs only.", exc)
        short.unlink(missing_ok=True)
        return None


# ===========================================================================
# Orchestration
# ===========================================================================

def run_one_matrix(
    sample_name: str,
    pairs: Path,
    genome: str,
    chrom_sizes: Path,
    output_dir: Path,
    *,
    base_binsize: int = DEFAULT_BASE_BINSIZE,
    resolutions: list[int] | None = None,
    nproc: int = 8,
    juicer_jar: Path | None = None,
    make_hic: bool = True,
) -> MatrixResult:
    resolutions = sorted(set(resolutions or DEFAULT_RESOLUTIONS) | {base_binsize})
    output_dir.mkdir(parents=True, exist_ok=True)

    base_cool = output_dir / f"{sample_name}.{base_binsize}.cool"
    cload_pairs(pairs, chrom_sizes, base_binsize, base_cool, genome=genome, nproc=nproc)

    return _finalize_matrix(
        sample_name, base_cool, chrom_sizes, output_dir,
        base_binsize=base_binsize, resolutions=resolutions,
        nproc=nproc, juicer_jar=juicer_jar, make_hic=make_hic, hic_pairs=pairs,
    )


def _finalize_matrix(
    sample_name: str,
    base_cool: Path,
    chrom_sizes: Path,
    output_dir: Path,
    *,
    base_binsize: int,
    resolutions: list[int],
    nproc: int,
    juicer_jar: Path | None,
    make_hic: bool,
    hic_pairs: Path | list[Path] | None,
    is_combined: bool = False,
    condition: str | None = None,
    members: list[str] | None = None,
) -> MatrixResult:
    """Balance + zoomify a base ``.cool`` → ``.mcool``, then P(s) QC + optional .hic.

    Shared by single-sample matrices (base cool from ``cooler cload``) and pooled
    per-condition matrices (base cool from ``cooler merge``).
    """
    mcool = output_dir / f"{sample_name}.mcool"

    balance_cool(base_cool, nproc=nproc)
    zoomify(base_cool, resolutions, mcool, nproc=nproc)

    hic = None
    if make_hic and hic_pairs is not None:
        hic = export_hic(hic_pairs, chrom_sizes, output_dir / f"{sample_name}.hic", juicer_jar=juicer_jar)

    return MatrixResult(
        sample_name=sample_name, cool=base_cool, mcool=mcool,
        base_binsize=base_binsize, resolutions=resolutions, balanced=True,
        hic=hic, expected_tsv=None, ps_png=None,
        is_combined=is_combined, condition=condition, members=members or [],
    )


def run_one_combined(
    condition: str,
    member_results: list[MatrixResult],
    chrom_sizes: Path,
    output_dir: Path,
    *,
    member_pairs: list[Path] | None = None,
    base_binsize: int = DEFAULT_BASE_BINSIZE,
    resolutions: list[int] | None = None,
    nproc: int = 8,
    juicer_jar: Path | None = None,
    make_hic: bool = True,
) -> MatrixResult:
    """Pool one condition's replicate matrices into a single combined matrix.

    Sums the replicate base ``.cool`` files (``cooler merge``) and finalises like
    any other matrix. The combined matrix has deeper coverage than any single
    replicate, which is what downstream loop / TAD / compartment calling needs.
    """
    resolutions = sorted(set(resolutions or DEFAULT_RESOLUTIONS) | {base_binsize})
    output_dir.mkdir(parents=True, exist_ok=True)

    sample_name = f"{condition}_combined"
    merged_cool = output_dir / f"{sample_name}.{base_binsize}.cool"
    cooler_merge(merged_cool, [r.cool for r in member_results])

    return _finalize_matrix(
        sample_name, merged_cool, chrom_sizes, output_dir,
        base_binsize=base_binsize, resolutions=resolutions,
        nproc=nproc, juicer_jar=juicer_jar, make_hic=make_hic,
        hic_pairs=list(member_pairs) if member_pairs else None,
        is_combined=True, condition=condition,
        members=[r.sample_name for r in member_results],
    )


def run_all_matrix(
    pairs_inputs: list[tuple[str, Path]],
    genome: str,
    chrom_sizes: Path,
    output_dir: Path,
    **kwargs,
) -> list[MatrixResult]:
    results: list[MatrixResult] = []
    for name, pairs in pairs_inputs:
        logger.info("Building matrix for %s ...", name)
        results.append(run_one_matrix(name, pairs, genome, chrom_sizes, output_dir / name, **kwargs))
    return results


def run_all_combined(
    per_sample: list[MatrixResult],
    sample_to_condition: dict[str, str],
    chrom_sizes: Path,
    output_dir: Path,
    *,
    pairs_by_sample: dict[str, Path] | None = None,
    **kwargs,
) -> list[MatrixResult]:
    """Build one pooled matrix per condition that has ≥2 replicates.

    Conditions with a single replicate are skipped — pooling one library would
    just duplicate it. ``kwargs`` mirror :func:`run_one_combined` (base_binsize,
    resolutions, ps_resolution, nproc, juicer_jar, make_hic).
    """
    by_condition: dict[str, list[MatrixResult]] = {}
    for r in per_sample:
        cond = sample_to_condition.get(r.sample_name)
        if cond is None:
            logger.warning("Sample %s has no condition in the sample sheet — not pooled.", r.sample_name)
            continue
        by_condition.setdefault(cond, []).append(r)

    pairs_by_sample = pairs_by_sample or {}
    combined: list[MatrixResult] = []
    for cond, members in by_condition.items():
        if len(members) < 2:
            logger.info("Condition %s has a single replicate — skipping pool.", cond)
            continue
        logger.info("Pooling %d replicates for condition %s ...", len(members), cond)
        member_pairs = [pairs_by_sample[m.sample_name] for m in members
                        if m.sample_name in pairs_by_sample]
        combined.append(run_one_combined(
            cond, members, chrom_sizes, output_dir / f"{cond}_combined",
            member_pairs=member_pairs or None, **kwargs,
        ))
    return combined


def write_matrix_summary(results: list[MatrixResult], output_dir: Path) -> Path:
    import pandas as pd
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [{
        "sample":       r.sample_name,
        "combined":     r.is_combined,
        "condition":    r.condition or "",
        "members":      ";".join(r.members),
        "mcool":        str(r.mcool),
        "base_binsize": r.base_binsize,
        "resolutions":  ",".join(str(x) for x in r.resolutions),
        "balanced":     r.balanced,
        "hic":          str(r.hic) if r.hic else "",
        "expected_tsv": str(r.expected_tsv) if r.expected_tsv else "",
    } for r in results]
    path = output_dir / "matrix_summary.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    logger.info("Matrix summary written: %s", path)
    return path


# ===========================================================================
# Internal subprocess helpers
# ===========================================================================

def _require(tool: str) -> None:
    if not shutil.which(tool):
        raise RuntimeError(f"'{tool}' not found in PATH.\nInstall: conda install -c conda-forge {tool}")


def _run(cmd: list[str], *, label: str) -> None:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}")


def _run_shell(cmd: str, *, label: str) -> None:
    logger.info("Running: %s", label)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    log_tool_output(cmd, result)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {result.returncode}):\n{result.stderr[-3000:]}")
