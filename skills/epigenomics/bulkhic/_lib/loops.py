"""
loops.py — Bulk Hi-C Step 4c: loops via Mustache (multi-resolution, no merge).

    mustache -f <mcool> -r <res> -pt <fdr> -d <max_dist>  → loops TSV → BEDPE

Mustache (scale-space blob detection) is the production loop caller. It is run
independently at each requested resolution (default 5 kb + 10 kb) and each
resolution's loops are kept as their own BEDPE — NO cross-resolution merge.

Mustache (mustache-hic) needs numpy<2, so it lives in a dedicated sibling conda
env ``omicsclaw_mustache``; this skill (in ``omicsclaw_bulkhic``, numpy≥2) calls
that env's ``mustache`` binary directly. An empty loop set is a valid (not
failed) result.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import viz

logger = logging.getLogger(__name__)

DEFAULT_RESOLUTIONS = [5000, 10000]
DEFAULT_FDR = 0.01          # mustache -pt (p-value threshold; MS uses 0.01)
DEFAULT_MAX_DIST = 2_000_000  # mustache -d (max loop-locus separation, bp)
MUSTACHE_ENV = "omicsclaw_mustache"


@dataclass
class LoopResult:
    sample_name:  str
    is_combined:  bool = False
    resolutions:  list[int] = field(default_factory=list)
    bedpe_by_res: dict = field(default_factory=dict)   # resolution(int) -> BEDPE Path
    n_by_res:     dict = field(default_factory=dict)    # resolution(int) -> loop count

    @property
    def n_loops(self) -> int:
        return sum(self.n_by_res.values())

    @property
    def any_bedpe(self) -> bool:
        return bool(self.bedpe_by_res)

    @property
    def primary_bedpe(self):
        """Finest-resolution BEDPE (smallest bin), for downstream pileup default."""
        if not self.bedpe_by_res:
            return None
        return self.bedpe_by_res[min(self.bedpe_by_res)]


def _mustache_bin() -> str | None:
    """Resolve the mustache binary in the sibling numpy<2 env (or PATH)."""
    cand = Path(sys.prefix).parent / MUSTACHE_ENV / "bin" / "mustache"
    if cand.exists():
        return str(cand)
    return shutil.which("mustache")


def _count_bedpe(path: Path) -> int:
    try:
        with open(path) as fh:
            return sum(1 for ln in fh if ln.strip() and not ln.startswith(("#", "chrom", "BIN1")))
    except OSError:
        return 0


def _tsv_to_bedpe(tsv: Path, bedpe: Path) -> int:
    """Convert a Mustache loops TSV → BEDPE (6 cols + name, FDR, detection_scale)."""
    import csv
    n = 0
    with open(tsv) as fin, open(bedpe, "w") as fout:
        rdr = csv.reader(fin, delimiter="\t")
        header = next(rdr, None)  # BIN1_CHR BIN1_START BIN1_END BIN2_CHROMOSOME BIN2_START BIN2_END FDR DETECTION_SCALE
        for row in rdr:
            if len(row) < 6 or not row[0]:
                continue
            c1, s1, e1, c2, s2, e2 = row[0:6]
            fdr = row[6] if len(row) > 6 else "."
            scale = row[7] if len(row) > 7 else "."
            fout.write(f"{c1}\t{s1}\t{e1}\t{c2}\t{s2}\t{e2}\tloop_{n}\t{fdr}\t{scale}\n")
            n += 1
    return n


def run_loops(
    sample_name: str,
    mcool: Path,
    resolutions: list[int],
    output_dir: Path,
    *,
    fdr: float = DEFAULT_FDR,
    max_dist: int = DEFAULT_MAX_DIST,
    nproc: int = 8,
    is_combined: bool = False,
) -> LoopResult:
    output_dir.mkdir(parents=True, exist_ok=True)   # loops/ base; per-resolution subdirs below
    res = LoopResult(sample_name=sample_name, is_combined=is_combined, resolutions=list(resolutions))

    mbin = _mustache_bin()
    if not mbin:
        logger.warning("mustache not found (expected sibling env '%s') — skipping loop calling. "
                       "Run 0_setup_env_for_bulkhic.sh.", MUSTACHE_ENV)
        return res

    uri = str(mcool)  # mustache reads .mcool directly with -r <resolution>
    for r in resolutions:
        rdir = output_dir / str(r); rdir.mkdir(parents=True, exist_ok=True)
        bedpe = rdir / f"{sample_name}.loops.{r}.bedpe"
        if bedpe.exists():
            logger.info("  [%s] checkpoint: loops BEDPE @%d exists — skipping mustache", sample_name, r)
            res.bedpe_by_res[r] = bedpe
            res.n_by_res[r] = _count_bedpe(bedpe)
            continue

        raw = rdir / f"{sample_name}.mustache.{r}.tsv"
        cmd = [mbin, "-f", uri, "-r", str(r), "-pt", str(fdr),
               "-d", str(max_dist), "-p", str(nproc), "-o", str(raw)]
        logger.info("  [%s] Running: mustache @%d  (%s)", sample_name, r, " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("  [%s] mustache @%d error (%s).", sample_name, r, exc)
            continue
        if raw.exists():
            n = _tsv_to_bedpe(raw, bedpe)
            res.bedpe_by_res[r] = bedpe
            res.n_by_res[r] = n
            logger.info("  [%s] @%d → %d loops", sample_name, r, n)
        elif proc.returncode == 0:
            # mustache succeeded but found nothing → empty BEDPE is a valid result.
            bedpe.write_text("")
            res.bedpe_by_res[r] = bedpe
            res.n_by_res[r] = 0
            logger.info("  [%s] @%d → 0 loops", sample_name, r)
        else:
            logger.warning("  [%s] mustache @%d failed (rc=%s): %s",
                           sample_name, r, proc.returncode, (proc.stderr or "")[-400:])
    return res


def _read_loop_bins(bedpe, resolution):
    """Intra-chromosomal loops from a BEDPE -> list of (chrom, i_bin, j_bin) at `resolution`."""
    out = []
    try:
        import pandas as pd
        if not Path(bedpe).exists() or Path(bedpe).stat().st_size == 0:
            return out
        df = pd.read_csv(bedpe, sep="\t", header=None, comment="#")
        for _, row in df.iterrows():
            c1, s1, c2, s2 = str(row[0]), int(row[1]), str(row[3]), int(row[4])
            if c1 != c2:
                continue
            i, j = s1 // resolution, s2 // resolution
            out.append((c1, min(i, j), max(i, j)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("loop BEDPE read failed (%s).", exc)
    return out


def _loop_spans_bp(bedpe):
    """Intra-chromosomal loop spans (bp) = |anchor2_start - anchor1_start|."""
    try:
        import pandas as pd
        if not Path(bedpe).exists() or Path(bedpe).stat().st_size == 0:
            return []
        df = pd.read_csv(bedpe, sep="\t", header=None, comment="#")
        df = df[df[0].astype(str) == df[3].astype(str)]
        spans = (df[4].astype(int) - df[1].astype(int)).abs()
        return spans[spans > 0].tolist()
    except Exception:  # noqa: BLE001
        return []


def plot_loop_size_distribution(results, out_dir, *, resolution=None, sample_sheet=None):
    """Loop size (anchor separation) as a VIOLIN per condition (log10 bp).

    Pass the condition (combined) samples only; the x labels carry each
    condition's loop count. Mirrors the production MS loop-size violin
    (2_loopSize_violinplot_usingLog10.py).
    """
    try:
        import numpy as np
        import pandas as pd
        rows = []
        for r in results:
            cond = viz.condition_of(r.sample_name, sample_sheet)
            bp = (r.bedpe_by_res.get(resolution) if resolution is not None
                  else None) or getattr(r, "primary_bedpe", None)
            for s in (_loop_spans_bp(bp) if bp else []):
                if s > 0:
                    rows.append((cond, float(np.log10(s))))
        if len(rows) < 2:
            return None
        df = pd.DataFrame(rows, columns=["condition", "log10size"])
        rl = f" @ {resolution // 1000} kb" if resolution else ""
        return viz.violin_size(df, out_dir, "loop_size_distribution",
                               ylabel="log10 loop size (bp)", title=f"Loop size{rl}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("loop_size_distribution failed (%s).", exc)
        return None


def _plot_loop_pca(scores, var, names, out_dir, sample_sheet, resolution, n_loops):
    try:
        import numpy as np
        import matplotlib.pyplot as plt
        viz.setup_plot_style()
        conds = [viz.condition_of(n, sample_sheet) for n in names]
        ucond = list(dict.fromkeys(conds))
        ccolor = {c: viz.PALETTE[i % len(viz.PALETTE)] for i, c in enumerate(ucond)}
        pc1 = scores[:, 0]; pc2 = scores[:, 1] if scores.shape[1] > 1 else np.zeros_like(pc1)
        rl = f"{resolution // 1000} kb" if resolution % 1000 == 0 else f"{resolution} bp"
        fig, ax = plt.subplots(figsize=(5, 4.5))
        seen = set()
        for i, n in enumerate(names):
            c = conds[i]
            ax.scatter(pc1[i], pc2[i], color=ccolor[c], s=40, edgecolor="white", lw=0.5,
                       zorder=3, label=c if c not in seen else None)
            seen.add(c)
            ax.annotate(n, (pc1[i], pc2[i]), fontsize=8, xytext=(4, 4), textcoords="offset points")
        ax.axhline(0, color="grey", lw=0.5, ls=":"); ax.axvline(0, color="grey", lw=0.5, ls=":")
        ax.set_xlabel(f"PC1 ({var[0] * 100:.0f}%)")
        ax.set_ylabel(f"PC2 ({var[1] * 100:.0f}%)" if len(var) > 1 else "PC2")
        ax.set_title(f"Loop strength PCA ({rl}, {n_loops} union loops)")
        ax.legend()
        return viz.save_figure(fig, "loop_pca", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("loop PCA plot failed (%s).", exc)
        return None


def run_loop_pca(loop_inputs, out_dir, *, resolution, sample_sheet=None):
    """Sample PCA on loop contact strength over the union loop set (UnionLoops-style).

    `loop_inputs` = list of (sample_name, bedpe_path, mcool_path). Builds the
    UNION of all samples' intra-chromosomal loop calls, scores each union loop
    by that sample's balanced contact at the loop pixel, then PCA (numpy SVD)
    across samples -> a PC1/PC2 scatter coloured by condition. Per-loop
    mean-centering removes the distance baseline, so raw balanced strength is
    a valid cross-sample feature.

    Sources / method:
      * Union candidate loop set across related Hi-C datasets - UnionLoops
        (Zhang et al., bioRxiv 2026; PMC12871756).
      * Sample/replicate PCA on loop contact strength (replicates co-cluster) -
        Hi-C loop-dynamics study, e.g. PMC10547260 (chromatin loop dynamics during
        differentiation; replicate similarity assessed by PCA + APA).
      * Quantile normalization - Bolstad et al., Bioinformatics 2003
        (doi:10.1093/bioinformatics/19.2.185).
    """
    try:
        import numpy as np
        import pandas as pd
        import cooler
        from collections import defaultdict
        from .compartments import _quantile_normalize
    except Exception as exc:  # noqa: BLE001
        logger.warning("deps unavailable (%s) — no loop PCA.", exc)
        return None
    inputs = [x for x in loop_inputs if x[1] and Path(x[1]).exists()]
    if len(inputs) < 3:
        logger.info("loop PCA skipped (need >=3 samples).")
        return None
    try:
        union = set()
        for _name, bedpe, _m in inputs:
            union |= set(_read_loop_bins(bedpe, resolution))
        union = sorted(union)
        if len(union) < 3:
            logger.info("loop PCA skipped (<3 union loops @ %d).", resolution)
            return None
        by_chrom = defaultdict(list)
        for k in union:
            by_chrom[k[0]].append(k)
        cols = {}
        for name, _bedpe, mcool in inputs:
            clr = cooler.Cooler(f"{mcool}::resolutions/{resolution}")
            vals = {}
            for c, keys in by_chrom.items():
                try:
                    M = clr.matrix(balance=True, sparse=True).fetch(c).tocsr()
                except Exception:  # noqa: BLE001
                    continue
                n = M.shape[0]
                for (_c, i, j) in keys:
                    vals[(_c, i, j)] = M[i, j] if (i < n and j < n) else np.nan
            cols[name] = pd.Series([vals.get(k, np.nan) for k in union])
        mat = pd.DataFrame(cols).replace([np.inf, -np.inf], np.nan).dropna()
        if mat.shape[0] < 3 or mat.shape[1] < 3:
            return None
        names = list(mat.columns)
        Xn = _quantile_normalize(np.log1p(mat.values))     # union x samples
        Xc = Xn.T - Xn.T.mean(axis=0, keepdims=True)        # samples x loops, centred per loop
        U, S, _ = np.linalg.svd(Xc, full_matrices=False)
        scores = U * S
        var = (S ** 2) / np.sum(S ** 2) if np.sum(S ** 2) > 0 else np.zeros_like(S)
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        ncomp = min(scores.shape[1], 5)
        pd.DataFrame(scores[:, :ncomp], index=names,
                     columns=[f"PC{i + 1}" for i in range(ncomp)]).to_csv(
            out_dir / "loop_pca_coords.tsv", sep="\t")
        png = _plot_loop_pca(scores, var, names, out_dir, sample_sheet, resolution, mat.shape[0])
        return {"png": str(png) if png else None, "coords": str(out_dir / "loop_pca_coords.tsv"),
                "var": [float(v) for v in var[:2]], "n_union_loops": int(mat.shape[0])}
    except Exception as exc:  # noqa: BLE001
        logger.warning("loop PCA failed (%s).", exc)
        return None


def plot_loops_all(results, out_dir):
    """≥2-sample comparison: loop-count bar (sample × resolution) + loop-size dist."""
    try:
        import numpy as np
        import pandas as pd
        import matplotlib.pyplot as plt
        if len(results) < 2:
            return None
        viz.setup_plot_style()
        names = [r.sample_name for r in results]
        colors = viz.sample_colors(names)
        resolutions = sorted({res for r in results for res in r.resolutions})
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4))
        x = np.arange(len(names))
        w = 0.8 / max(1, len(resolutions))
        for i, res in enumerate(resolutions):
            off = (i - (len(resolutions) - 1) / 2) * w
            ax1.bar(x + off, [r.n_by_res.get(res, 0) for r in results], w,
                    label=f"{res // 1000} kb")
        ax1.set_xticks(x); ax1.set_xticklabels(names, rotation=45, ha="right")
        ax1.set_ylabel("loops called"); ax1.set_title("Loop counts"); ax1.legend(title="resolution")
        # loop-size distribution (pool resolutions per sample)
        plotted = False
        for r in results:
            sizes = []
            for res, bedpe in r.bedpe_by_res.items():
                bedpe = Path(bedpe)
                if not bedpe.exists() or bedpe.stat().st_size == 0:
                    continue
                try:
                    df = pd.read_csv(bedpe, sep="\t", header=None)
                    mid1 = (df[1] + df[2]) / 2.0
                    mid2 = (df[4] + df[5]) / 2.0
                    s = (mid2 - mid1).abs() / 1000.0
                    sizes.extend(s[s > 0].tolist())
                except Exception:  # noqa: BLE001
                    pass
            if sizes:
                ax2.hist(np.log10(sizes), bins=30, histtype="step", lw=2, density=True,
                         color=colors[r.sample_name], label=r.sample_name)
                plotted = True
        ax2.set_xlabel("log10 loop size (kb)"); ax2.set_ylabel("density")
        ax2.set_title("Loop size distribution")
        if plotted:
            ax2.legend()
        return viz.save_figure(fig, "loops_all", out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("loops_all failed (%s).", exc)
        return None
