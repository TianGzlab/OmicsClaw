#!/usr/bin/env python3
"""Spatial Genes — find spatially variable genes via multiple methods.

Supported methods:
  - morans:    Moran's I spatial autocorrelation via Squidpy (default, fast)
  - spatialde: Gaussian process regression via SpatialDE2 (identifies patterns)
  - sparkx:    Non-parametric kernel test via SPARK-X in R (rpy2 required)
  - flashs:    Randomized kernel approximation (Python native, fast on large data)

Usage:
    python spatial_genes.py --input <processed.h5ad> --output <dir>
    python spatial_genes.py --demo --output <dir>
    python spatial_genes.py --input <file> --method spatialde --output <dir>
    python spatial_genes.py --input <file> --method sparkx --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.spatial.adata_utils import (
    get_spatial_key,
    require_spatial_coords,
    store_analysis_metadata,
)
from omicsclaw.spatial.dependency_manager import require
from omicsclaw.spatial.viz_utils import save_figure
from omicsclaw.spatial.viz import VizParams, plot_features, plot_spatial_stats

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-genes"
SKILL_VERSION = "0.2.0"

SUPPORTED_METHODS = ("morans", "spatialde", "sparkx", "flashs")


# ---------------------------------------------------------------------------
# Helper: extract dense expression for a subset of genes (memory-efficient)
# ---------------------------------------------------------------------------


def _get_dense_expression(adata, gene_mask: np.ndarray | None = None) -> np.ndarray:
    """Return a dense (n_obs, n_genes) array, optionally subsetting columns."""
    X = adata.X
    if gene_mask is not None:
        X = X[:, gene_mask]
    if sparse.issparse(X):
        return X.toarray()
    return np.asarray(X)


# ---------------------------------------------------------------------------
# Core: Moran's I
# ---------------------------------------------------------------------------


def run_morans(
    adata,
    *,
    n_top_genes: int = 20,
    fdr_threshold: float = 0.05,
    n_neighs: int = 6,
    n_perms: int = 100,
) -> tuple[pd.DataFrame, dict]:
    """Compute Moran's I for all genes and return ranked SVG table + summary."""
    import squidpy as sq

    spatial_key = require_spatial_coords(adata)
    logger.info(
        "Computing spatial autocorrelation (Moran's I) for %d genes ...",
        adata.n_vars,
    )

    sq.gr.spatial_neighbors(adata, n_neighs=n_neighs, coord_type="generic", spatial_key=spatial_key)

    sq.gr.spatial_autocorr(
        adata,
        mode="moran",
        n_perms=n_perms,
        n_jobs=1,
    )

    if "moranI" not in adata.uns:
        raise RuntimeError(
            "squidpy.gr.spatial_autocorr did not produce 'moranI' results.\n"
            "Check that spatial coordinates are in adata.obsm (run spatial-preprocess first)."
        )

    df = adata.uns["moranI"].copy()
    df["gene"] = df.index

    if "pval_norm" in df.columns:
        sig = df[(df["I"] > 0) & (df["pval_norm"] < fdr_threshold)].copy()
    else:
        sig = df[df["I"] > 0].copy()

    sig = sig.sort_values("I", ascending=False)
    top = sig.head(n_top_genes)

    n_total = len(df)
    n_significant = len(sig)

    summary = {
        "method": "morans",
        "n_genes_tested": n_total,
        "n_significant": n_significant,
        "n_top_reported": len(top),
        "fdr_threshold": fdr_threshold,
        "top_genes": top["gene"].tolist(),
    }

    logger.info(
        "Moran's I: %d/%d genes significant (FDR < %.2f), reporting top %d",
        n_significant,
        n_total,
        fdr_threshold,
        len(top),
    )

    return df, summary


# ---------------------------------------------------------------------------
# Core: SpatialDE — Gaussian-process based SVG detection
# ---------------------------------------------------------------------------


def run_spatialde(
    adata,
    *,
    n_top_genes: int = 20,
    fdr_threshold: float = 0.05,
    omnibus: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """SpatialDE SVG detection with Gaussian process regression.

    Re-implemented following the official Teichlab/SpatialDE GitHub tutorial:
    https://github.com/Teichlab/SpatialDE

    Pipeline:
      1. NaiveDE.stabilize — Anscombe variance-stabilizing transform
      2. NaiveDE.regress_out — regress library size (total_counts)
      3. SpatialDE.run — GP-based spatial DE test
      4. (optional) SpatialDE.spatial_patterns — AEH pattern assignment

    Key output columns:
      - g: gene name
      - pval / qval: raw / FDR-corrected p-value
      - l: lengthscale (spatial distance of expression change)
      - FSV: fraction of variance explained by spatial variation
      - LLR: log-likelihood ratio
    """
    # --- scipy compat shims for SpatialDE 1.x ---
    # IMPORTANT: These shims MUST run BEFORE require() AND import SpatialDE,
    # because SpatialDE/base.py does `from scipy.misc import derivative` at
    # module load time, and SpatialDE/util.py uses `import scipy as sp` then
    # calls sp.arange, sp.array, sp.argsort, sp.zeros_like which were removed
    # in scipy >= 1.14.
    import scipy as _scipy
    _NUMPY_COMPAT_ATTRS = [
        "arange", "array", "argsort", "bool_", "concatenate", "diag", "dot",
        "empty", "exp", "eye", "float64", "inf", "int32", "log", "log2",
        "newaxis", "ones", "sqrt", "sum", "zeros", "zeros_like", "isnan",
        "nan", "pi", "linspace", "meshgrid",
    ]
    for _attr in _NUMPY_COMPAT_ATTRS:
        if not hasattr(_scipy, _attr) and hasattr(np, _attr):
            setattr(_scipy, _attr, getattr(np, _attr))

    # scipy.misc.derivative — removed in scipy >= 1.14, needed by base.py
    import scipy.misc as _scipy_misc
    if not hasattr(_scipy_misc, "derivative"):

        def _derivative_compat(func, x0, dx=1.0, n=1, args=(), order=3):
            """Central-difference numerical derivative (scipy.misc compat)."""
            if n == 1:
                return (func(x0 + dx, *args) - func(x0 - dx, *args)) / (2.0 * dx)
            if n == 2:
                return (
                    func(x0 + dx, *args)
                    - 2.0 * func(x0, *args)
                    + func(x0 - dx, *args)
                ) / dx**2
            from math import comb
            ho = order >> 1
            weights = np.array(
                [(-1) ** (n - k + ho) * comb(n, abs(k - ho)) for k in range(order)],
                dtype=float,
            )
            vals = np.array(
                [func(x0 + (k - ho) * dx, *args) for k in range(order)]
            )
            return np.dot(weights, vals) / dx**n

        _scipy_misc.derivative = _derivative_compat

    # NOW safe to require/import
    require("spatialde", feature="SpatialDE spatially variable gene detection")
    import SpatialDE
    import NaiveDE

    # ----- Prepare data (following official tutorial) -----
    spatial_key = require_spatial_coords(adata)
    coords = adata.obsm[spatial_key]

    logger.info("Running SpatialDE on %d genes ...", adata.n_vars)

    # Build counts DataFrame (samples × genes)
    adata_work = adata.copy()
    if sparse.issparse(adata_work.X):
        adata_work.X = adata_work.X.toarray()

    counts = pd.DataFrame(
        adata_work.X,
        index=adata_work.obs_names,
        columns=adata_work.var_names,
    )

    # Filter practically unobserved genes (official: counts.sum(0) >= 3)
    gene_totals = counts.sum(axis=0)
    counts = counts.T[gene_totals >= 3].T
    if counts.shape[1] == 0:
        raise ValueError("All genes have < 3 total counts — cannot run SpatialDE.")
    logger.info("SpatialDE: %d genes remain after count filter (>= 3)", counts.shape[1])

    # Build sample_info with spatial coords + total_counts
    sample_info = pd.DataFrame(
        {"x": coords[:, 0], "y": coords[:, 1], "total_counts": counts.sum(axis=1)},
        index=adata_work.obs_names,
    )

    # Step 1 — Anscombe variance-stabilizing transform (official tutorial)
    # NaiveDE.stabilize expects genes × samples (rows=genes), returns same
    norm_expr = NaiveDE.stabilize(counts.T).T

    # Step 2 — Regress out per-cell library size (official tutorial)
    resid_expr = NaiveDE.regress_out(
        sample_info, norm_expr.T, "np.log(total_counts)"
    ).T

    # Step 3 — Drop zero-variance genes (constant after regress_out → degenerate GP)
    gene_var = resid_expr.var(axis=0)
    resid_expr = resid_expr.loc[:, gene_var > 0]
    if resid_expr.shape[1] == 0:
        raise ValueError(
            "All genes have zero variance after normalization — cannot run SpatialDE."
        )
    logger.info("SpatialDE: %d genes pass variance filter", resid_expr.shape[1])

    # Step 4 — Run SpatialDE GP test (official: SpatialDE.run(X, resid_expr))
    X = sample_info[["x", "y"]]
    results = SpatialDE.run(X, resid_expr)

    # Step 5 — Optional: AEH (Automatic Expression Histology)
    # Groups significant genes into spatial co-expression patterns
    aeh_results = None
    aeh_patterns = None
    if omnibus:
        sign_results = results.query("qval < @fdr_threshold")
        if len(sign_results) >= 5:
            # Use median optimal lengthscale from significant genes
            l_aeh = float(sign_results["l"].median())
            n_patterns = min(max(3, len(sign_results) // 10), 10)
            try:
                logger.info(
                    "Running AEH: %d significant genes, %d patterns, l=%.2f",
                    len(sign_results), n_patterns, l_aeh,
                )
                aeh_results, aeh_patterns = SpatialDE.spatial_patterns(
                    X, resid_expr, sign_results, C=n_patterns, l=l_aeh, verbosity=0,
                )
            except Exception as aeh_err:
                logger.warning("AEH failed (non-fatal): %s", aeh_err)

    # ----- Format results -----
    results = results.sort_values("qval")

    col_map = {"g": "gene", "qval": "pval_norm", "LLR": "I"}
    df = results.rename(columns=col_map)
    if "gene" not in df.columns and "g" in results.columns:
        df["gene"] = results["g"]
    df = df.set_index("gene", drop=False)

    sig = df[df["pval_norm"] < fdr_threshold].copy()
    top = sig.head(n_top_genes)

    summary = {
        "method": "spatialde",
        "n_genes_tested": len(df),
        "n_significant": len(sig),
        "n_top_reported": len(top),
        "fdr_threshold": fdr_threshold,
        "top_genes": top["gene"].tolist(),
    }

    if aeh_results is not None:
        n_patterns = int(aeh_results["pattern"].nunique())
        summary["aeh_patterns"] = n_patterns
        logger.info("AEH assigned %d genes to %d spatial patterns", len(aeh_results), n_patterns)

    # Store full results for downstream use
    adata.uns["spatialde_results"] = results
    if aeh_results is not None:
        adata.uns["spatialde_aeh"] = aeh_results
    if aeh_patterns is not None:
        adata.uns["spatialde_patterns"] = aeh_patterns

    logger.info(
        "SpatialDE: %d/%d genes significant (qval < %.2f), reporting top %d",
        len(sig), len(df), fdr_threshold, len(top),
    )

    return df, summary


# ---------------------------------------------------------------------------
# Core: SPARK-X — non-parametric R-based SVG test via rpy2
# ---------------------------------------------------------------------------


def run_sparkx(
    adata,
    *,
    n_top_genes: int = 20,
    fdr_threshold: float = 0.05,
    n_max_genes: int = 5000,
) -> tuple[pd.DataFrame, dict]:
    """SPARK-X non-parametric kernel test for SVG detection.

    SPARK-X is fast and distribution-free, making it suitable for large datasets.
    Requires R with the SPARK package installed, accessed via rpy2.
    """
    require("rpy2", feature="SPARK-X SVG detection (R interface)")

    import rpy2.robjects as ro
    from rpy2.robjects import numpy2ri, pandas2ri
    from rpy2.robjects.packages import importr

    numpy2ri.activate()
    pandas2ri.activate()

    try:
        spark = importr("SPARK")
    except Exception:
        raise ImportError(
            "R package 'SPARK' is not installed. Install it in R with:\n"
            "  devtools::install_github('xzhoulab/SPARK')"
        )

    spatial_key = require_spatial_coords(adata)
    coords = adata.obsm[spatial_key][:, :2]

    if adata.n_vars > n_max_genes:
        logger.info("Subsetting to top %d highly variable genes for SPARK-X", n_max_genes)
        if "highly_variable" in adata.var.columns:
            hvg_mask = adata.var["highly_variable"].values
            if hvg_mask.sum() > n_max_genes:
                hvg_idx = np.where(hvg_mask)[0][:n_max_genes]
                hvg_mask = np.zeros(adata.n_vars, dtype=bool)
                hvg_mask[hvg_idx] = True
        else:
            gene_var = np.var(_get_dense_expression(adata), axis=0)
            top_idx = np.argsort(gene_var)[-n_max_genes:]
            hvg_mask = np.zeros(adata.n_vars, dtype=bool)
            hvg_mask[top_idx] = True
        adata_sub = adata[:, hvg_mask].copy()
    else:
        adata_sub = adata

    X_dense = _get_dense_expression(adata_sub)
    gene_names = list(adata_sub.var_names)

    logger.info("Running SPARK-X on %d genes ...", len(gene_names))

    r_counts = ro.r["matrix"](
        ro.FloatVector(X_dense.T.flatten()),
        nrow=len(gene_names),
        ncol=adata_sub.n_obs,
    )
    r_counts.rownames = ro.StrVector(gene_names)

    r_coords = ro.r["matrix"](
        ro.FloatVector(coords.flatten()),
        nrow=coords.shape[0],
        ncol=2,
    )

    sparkx_result = spark.sparkx(
        r_counts, r_coords,
        numCores=1,
        option="mixture",
    )

    res_df = pandas2ri.rpy2py(sparkx_result.rx2("res_mtest"))
    res_df["gene"] = gene_names
    res_df = res_df.rename(columns={
        "combinedPval": "pval_norm",
        "adjustedPval": "qval",
    })
    res_df["I"] = -np.log10(res_df["pval_norm"].clip(lower=1e-300))
    res_df = res_df.set_index("gene", drop=False)
    res_df = res_df.sort_values("pval_norm")

    numpy2ri.deactivate()
    pandas2ri.deactivate()

    sig = res_df[res_df["pval_norm"] < fdr_threshold].copy()
    top = sig.head(n_top_genes)

    summary = {
        "method": "sparkx",
        "n_genes_tested": len(res_df),
        "n_significant": len(sig),
        "n_top_reported": len(top),
        "fdr_threshold": fdr_threshold,
        "top_genes": top["gene"].tolist(),
    }

    logger.info(
        "SPARK-X: %d/%d genes significant (p < %.2f), reporting top %d",
        len(sig), len(res_df), fdr_threshold, len(top),
    )

    return res_df, summary


# ---------------------------------------------------------------------------
# Core: FlashS — randomized kernel approximation (Python native)
# ---------------------------------------------------------------------------


def run_flashs(
    adata,
    *,
    n_top_genes: int = 20,
    fdr_threshold: float = 0.05,
    n_rand_features: int = 500,
) -> tuple[pd.DataFrame, dict]:
    """FlashS randomized-kernel SVG detection (Python native, fast).

    Approximates the spatial kernel matrix using random Fourier features
    for O(n * m) complexity instead of O(n^2), making it suitable for
    datasets with >50k spots.
    """
    from scipy.stats import chi2

    spatial_key = require_spatial_coords(adata)
    coords = adata.obsm[spatial_key][:, :2].astype(np.float64)

    n_obs, n_genes = adata.shape
    logger.info("Running FlashS on %d genes (%d spots) ...", n_genes, n_obs)

    bandwidth = np.median(np.std(coords, axis=0))
    if bandwidth < 1e-10:
        bandwidth = 1.0

    rng = np.random.RandomState(42)
    m = n_rand_features
    omega = rng.randn(2, m) / bandwidth
    phase = rng.uniform(0, 2 * np.pi, m)

    Z = np.sqrt(2.0 / m) * np.cos(coords @ omega + phase)
    Z = Z - Z.mean(axis=0)

    X_dense = _get_dense_expression(adata)
    X_centered = X_dense - X_dense.mean(axis=0)

    XtZ = X_centered.T @ Z
    stat = np.sum(XtZ ** 2, axis=1) / n_obs

    df_chi2 = m
    pvalues = 1 - chi2.cdf(stat * n_obs, df=df_chi2)

    from statsmodels.stats.multitest import multipletests
    _, qvalues, _, _ = multipletests(pvalues, method="fdr_bh")

    df = pd.DataFrame({
        "gene": adata.var_names,
        "I": stat,
        "pval_norm": pvalues,
        "qval": qvalues,
    })
    df = df.set_index("gene", drop=False)
    df = df.sort_values("pval_norm")

    sig = df[df["pval_norm"] < fdr_threshold].copy()
    top = sig.head(n_top_genes)

    summary = {
        "method": "flashs",
        "n_genes_tested": len(df),
        "n_significant": len(sig),
        "n_top_reported": len(top),
        "fdr_threshold": fdr_threshold,
        "n_random_features": n_rand_features,
        "bandwidth": float(bandwidth),
        "top_genes": top["gene"].tolist(),
    }

    logger.info(
        "FlashS: %d/%d genes significant (p < %.2f), reporting top %d",
        len(sig), len(df), fdr_threshold, len(top),
    )

    return df, summary


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(
    adata,
    output_dir: Path,
    top_genes: list[str],
) -> list[str]:
    """Generate spatial feature maps for top SVGs + Moran's I ranking plot."""
    figures = []
    spatial_key = get_spatial_key(adata)

    if spatial_key and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm[spatial_key]

    genes_to_plot = [g for g in top_genes[:8] if g in adata.var_names]

    # 1. Multi-panel spatial feature maps for top SVGs
    if genes_to_plot and spatial_key is not None:
        try:
            fig = plot_features(
                adata,
                VizParams(
                    feature=genes_to_plot,
                    basis="spatial",
                    colormap="magma",
                    title="Top Spatially Variable Genes",
                    show_colorbar=True,
                ),
            )
            p = save_figure(fig, output_dir, "top_svg_spatial.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate SVG spatial multi-panel: %s", exc)

    # 2. Moran's I ranking barplot
    if "moranI" in adata.uns:
        try:
            fig = plot_spatial_stats(adata, subtype="moran")
            p = save_figure(fig, output_dir, "moran_ranking.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate Moran ranking plot: %s", exc)

    # 3. UMAP view of top SVGs (if available)
    if genes_to_plot and "X_umap" in adata.obsm:
        try:
            fig = plot_features(
                adata,
                VizParams(
                    feature=genes_to_plot[:6],
                    basis="umap",
                    colormap="magma",
                    title="Top SVGs on UMAP",
                    show_colorbar=True,
                ),
            )
            p = save_figure(fig, output_dir, "top_svg_umap.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate SVG UMAP: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path,
    svg_df: pd.DataFrame,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write report.md, result.json, tables/svg_results.csv, reproducibility."""

    header = generate_report_header(
        title="Spatially Variable Genes Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "FDR threshold": str(summary["fdr_threshold"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Genes tested**: {summary['n_genes_tested']}",
        f"- **Significant SVGs** (FDR < {summary['fdr_threshold']}): {summary['n_significant']}",
        f"- **Top genes reported**: {summary['n_top_reported']}",
    ]

    if "note" in summary:
        body_lines.extend(["", f"> **Note**: {summary['note']}"])

    body_lines.extend(["", "### Top spatially variable genes\n"])

    has_pval = "pval_norm" in svg_df.columns
    if has_pval:
        body_lines.append("| Rank | Gene | Moran's I | p-value |")
        body_lines.append("|------|------|-----------|---------|")
    else:
        body_lines.append("| Rank | Gene | Score |")
        body_lines.append("|------|------|-------|")

    top_genes = summary["top_genes"]
    for rank, gene in enumerate(top_genes[:20], 1):
        if gene in svg_df.index:
            row = svg_df.loc[gene]
            i_val = row["I"]
            if has_pval:
                pval = row.get("pval_norm", float("nan"))
                body_lines.append(f"| {rank} | {gene} | {i_val:.4f} | {pval:.2e} |")
            else:
                body_lines.append(f"| {rank} | {gene} | {i_val:.4f} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer

    report_path = output_dir / "report.md"
    report_path.write_text(report)
    logger.info("Wrote %s", report_path)

    # result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data={"params": params, **summary},
        input_checksum=checksum,
    )

    # tables/svg_results.csv
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    csv_df = svg_df.copy()
    if "gene" not in csv_df.columns:
        csv_df["gene"] = csv_df.index
    cols = ["gene", "I"]
    for col in ["pval_norm", "var_norm", "pval_z_sim", "pval_sim", "var_sim"]:
        if col in csv_df.columns:
            cols.append(col)
    csv_df = csv_df[[c for c in cols if c in csv_df.columns]]
    csv_df.to_csv(tables_dir / "svg_results.csv", index=False)
    logger.info("Wrote %s", tables_dir / "svg_results.csv")

    # reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_genes.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    env_lines = []
    for pkg in ["scanpy", "anndata", "squidpy", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data (via spatial-preprocess --demo)
# ---------------------------------------------------------------------------


def get_demo_data(output_dir: Path) -> tuple:
    """Run spatial-preprocess --demo and load the resulting processed.h5ad."""
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"

    with tempfile.TemporaryDirectory(prefix="svg_demo_") as tmpdir:
        tmpdir = Path(tmpdir)
        cmd = [
            sys.executable,
            str(preprocess_script),
            "--demo",
            "--output", str(tmpdir),
        ]
        logger.info("Running spatial-preprocess --demo ...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error("spatial-preprocess failed:\n%s", result.stderr)
            raise RuntimeError(f"spatial-preprocess --demo failed: {result.stderr}")

        h5ad_path = tmpdir / "processed.h5ad"
        if not h5ad_path.exists():
            raise FileNotFoundError(
                f"spatial-preprocess did not produce {h5ad_path}"
            )

        adata = sc.read_h5ad(h5ad_path)

        # Copy the preprocessed file to output for reference
        dest = output_dir / "processed.h5ad"
        if not dest.exists():
            import shutil
            shutil.copy2(h5ad_path, dest)

    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


from typing import Callable

_METHOD_DISPATCH: dict[str, Callable] = {
    "morans": run_morans,
    "spatialde": run_spatialde,
    "sparkx": run_sparkx,
    "flashs": run_flashs,
}


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Genes — multi-method spatially variable gene detection",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method",
        choices=list(SUPPORTED_METHODS),
        default="morans",
        help=f"SVG detection method (default: morans). Options: {', '.join(SUPPORTED_METHODS)}",
    )
    parser.add_argument(
        "--n-top-genes",
        type=int,
        default=20,
        help="Number of top SVGs to report (default: 20)",
    )
    parser.add_argument(
        "--fdr-threshold",
        type=float,
        default=0.05,
        help="FDR p-value cutoff (default: 0.05)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data(output_dir)
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    params = {
        "method": args.method,
        "n_top_genes": args.n_top_genes,
        "fdr_threshold": args.fdr_threshold,
    }

    run_fn = _METHOD_DISPATCH[args.method]
    svg_df, summary = run_fn(
        adata,
        n_top_genes=args.n_top_genes,
        fdr_threshold=args.fdr_threshold,
    )

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params=params,
    )

    top_genes = summary.get("top_genes", [])

    generate_figures(adata, output_dir, top_genes)
    write_report(output_dir, svg_df, summary, input_file, params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"SVG detection complete: {summary['n_significant']} significant genes "
        f"({summary['method']}, FDR < {summary['fdr_threshold']})"
    )


if __name__ == "__main__":
    main()
