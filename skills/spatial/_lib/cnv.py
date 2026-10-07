"""Spatial CNV inference functions.

Provides inferCNVpy and Numbat for copy number variation analysis.

Input matrix convention (per-method):
  - infercnvpy: adata.X (log-normalized) — computes log-fold-change vs reference
  - numbat:     adata.layers["counts"] (raw integer UMI) — count-based CNV model,
                plus allele counts and normalized reference expression

Usage::

    from skills.spatial._lib.cnv import run_cnv, SUPPORTED_METHODS
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import sparse

from skills._sdk.deps import require

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("infercnvpy", "numbat")

# Numbat requires raw integer counts; infercnvpy uses log-normalized adata.X.
COUNT_BASED_METHODS = ("numbat",)

INFERCNVPY_DEFAULT_EXCLUDE_CHROMOSOMES = ("chrX", "chrY")
VALID_NUMBAT_GENOMES = ("hg19", "hg38")

METHOD_PARAM_DEFAULTS = {
    "infercnvpy": {
        "window_size": 100,
        "step": 10,
        "lfc_clip": 3.0,
        "dynamic_threshold": 1.5,
        "exclude_chromosomes": list(INFERCNVPY_DEFAULT_EXCLUDE_CHROMOSOMES),
        "chunksize": 5000,
        "n_jobs": 1,
        "neighbors_k": 15,
        "leiden_resolution": 1.0,
    },
    "numbat": {
        "genome": "hg38",
        "max_entropy": 0.8,
        "min_llr": 5.0,
        "min_cells": 50,
        "ncores": 1,
    },
}


def _get_counts_layer(adata) -> str | None:
    """Return the name of the raw-counts layer, or None if unavailable.

    Looks for ``layers["counts"]`` (standard convention set by preprocessing).
    Falls back to ``adata.raw`` by copying into a temporary layer.
    """
    if "counts" in adata.layers:
        return "counts"
    if adata.raw is not None:
        logger.info("No 'counts' layer found; copying from adata.raw")
        adata.layers["counts"] = adata.raw.X.copy()
        return "counts"
    return None


def _normalize_exclude_chromosomes(value) -> list[str] | None:
    """Normalize chromosome exclusions to a flat string list or ``None``."""
    if value is None:
        return None

    if isinstance(value, str):
        tokens = [tok.strip() for tok in value.split(",")]
    else:
        tokens = []
        for item in value:
            if item is None:
                continue
            tokens.extend(str(item).split(","))

    normalized = [tok.strip() for tok in tokens if str(tok).strip()]
    return normalized or None


def _get_allele_counts_df(adata, allele_counts=None) -> pd.DataFrame:
    """Return validated allele counts table for Numbat."""
    if allele_counts is None and "allele_counts" not in adata.obsm:
        raise ValueError("Numbat requires allele count data in adata.obsm['allele_counts']")

    if allele_counts is None:
        allele_counts = adata.obsm["allele_counts"]
    if isinstance(allele_counts, pd.DataFrame):
        df = allele_counts.copy()
    elif hasattr(allele_counts, "to_pandas"):
        df = allele_counts.to_pandas()
    else:
        raise ValueError(
            "adata.obsm['allele_counts'] must be a pandas DataFrame-like table "
            "with columns cell/snp_id/CHROM/POS/AD/DP/GT/gene"
        )

    required_cols = {"cell", "snp_id", "CHROM", "POS", "AD", "DP", "GT", "gene"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            "Numbat allele counts table is missing required columns: "
            f"{sorted(missing)}"
        )

    df = df.copy()
    df["cell"] = df["cell"].astype(str)
    if not set(df["cell"]) <= set(adata.obs_names):
        raise ValueError("Allele counts contain cells absent from adata.obs_names")
    return df


def validate_reference(adata, reference_key: str | None, reference_cat: list[str]) -> None:
    """Validate that reference key and categories exist in adata."""
    if reference_key is None:
        return
    if reference_key not in adata.obs.columns:
        raise ValueError(f"'{reference_key}' not in adata.obs. Available: {list(adata.obs.columns)}")
    avail = set(adata.obs[reference_key].unique())
    missing = set(reference_cat) - avail
    if missing:
        raise ValueError(f"Categories {sorted(missing)} not in '{reference_key}'. Available: {sorted(avail)}")


def run_infercnvpy(adata, *, reference_key: str | None = None, reference_cat: list[str] | None = None,
                   window_size: int = METHOD_PARAM_DEFAULTS["infercnvpy"]["window_size"],
                   step: int = METHOD_PARAM_DEFAULTS["infercnvpy"]["step"],
                   dynamic_threshold: float | None = METHOD_PARAM_DEFAULTS["infercnvpy"]["dynamic_threshold"],
                   lfc_clip: float = METHOD_PARAM_DEFAULTS["infercnvpy"]["lfc_clip"],
                   exclude_chromosomes=None,
                   chunksize: int = METHOD_PARAM_DEFAULTS["infercnvpy"]["chunksize"],
                   n_jobs: int | None = METHOD_PARAM_DEFAULTS["infercnvpy"]["n_jobs"],
                   leiden_resolution: float = METHOD_PARAM_DEFAULTS["infercnvpy"]["leiden_resolution"],
                   neighbors_k: int = METHOD_PARAM_DEFAULTS["infercnvpy"]["neighbors_k"],
                   random_state: int = 0) -> dict:
    """Infer CNV using inferCNVpy.

    Uses ``adata.X`` (log-normalized) — inferCNVpy subtracts the reference
    expression in log-space (equivalent to log-fold-change) and smooths across
    genomic windows.  The method explicitly requires normalized, log-transformed
    input per its documentation.

    Also requires gene genomic position annotations (chromosome, start, end)
    in ``adata.var`` and optionally a reference cell group in ``adata.obs``.
    """
    require("infercnvpy", feature="CNV inference")
    import infercnvpy as cnv
    import scanpy as sc

    req_cols = {"chromosome", "start", "end"}
    if not req_cols.issubset(adata.var.columns):
        missing = req_cols - set(adata.var.columns)
        raise ValueError(
            f"inferCNVpy requires genomic annotations. Missing adata.var columns: {list(missing)}. "
            "Please ensure gene positions are mapped before running CNV."
        )

    exclude_chromosomes = _normalize_exclude_chromosomes(exclude_chromosomes)

    logger.info(
        "Running inferCNVpy on adata.X (log-normalized), window=%d, step=%d, dynamic_threshold=%s",
        window_size,
        step,
        dynamic_threshold,
    )
    cnv.tl.infercnv(
        adata,
        reference_key=reference_key,
        reference_cat=reference_cat,
        window_size=window_size,
        step=step,
        dynamic_threshold=dynamic_threshold,
        lfc_clip=lfc_clip,
        exclude_chromosomes=exclude_chromosomes,
        chunksize=chunksize,
        n_jobs=n_jobs,
    )

    # infercnvpy's cnv_score() expects CNV-space clustering labels in
    # adata.obs['cnv_leiden'], so build the standard PCA -> neighbors ->
    # Leiden chain after infercnv() finishes.
    logger.info("Computing CNV PCA / neighbors / Leiden before CNV scoring...")
    cnv.tl.pca(adata, random_state=random_state)
    cnv_rep_key = None
    for candidate in ("X_cnv_pca", "cnv_pca", "X_cnv"):
        if candidate in adata.obsm:
            cnv_rep_key = candidate
            break

    if adata.n_obs <= 2:
        n_neighbors = 1
    else:
        n_neighbors = max(2, min(int(neighbors_k), adata.n_obs - 1))
    fallback = {}
    try:
        if cnv_rep_key is None:
            raise KeyError(
                "Did not find X_cnv_pca, cnv_pca, or X_cnv in adata.obsm after infercnvpy.tl.pca()."
            )
        sc.pp.neighbors(
            adata,
            use_rep=cnv_rep_key,
            key_added="cnv_neighbors",
            n_neighbors=n_neighbors,
            random_state=random_state,
        )
        cnv.tl.leiden(adata, resolution=leiden_resolution, random_state=random_state)
    except Exception as exc:
        fallback = {"requested_method": "cnv_leiden", "executed_method": "single_group_cnv_score", "fallback_reason": str(exc)}
        logger.warning(
            "CNV Leiden clustering failed (%s). Falling back to a single CNV group for cnv_score().",
            exc,
        )
        adata.obs["cnv_leiden"] = pd.Categorical(np.repeat("cnv_all", adata.n_obs))

    logger.info("Computing overall CNV anomaly scores per cell...")
    cnv.tl.cnv_score(adata, groupby="cnv_leiden", use_rep="cnv")

    cnv_score_col = "cnv_score" if "cnv_score" in adata.obs.columns else None

    if cnv_score_col:
        # Fill any NaNs that might have emerged during sliding window edge cases
        if adata.obs[cnv_score_col].isna().any():
            adata.obs[cnv_score_col] = adata.obs[cnv_score_col].fillna(0.0)

        mean_score = float(adata.obs[cnv_score_col].mean())
        threshold = float(adata.obs[cnv_score_col].quantile(0.9))
        high_cnv_pct = float((adata.obs[cnv_score_col] > threshold).mean() * 100)
    else:
        mean_score = 0.0
        high_cnv_pct = 0.0

    return {
        "method": "infercnvpy",
        "n_genes": adata.n_vars,
        "mean_cnv_score": float(f"{mean_score:.4f}"),
        "high_cnv_fraction_pct": float(f"{high_cnv_pct:.2f}"),
        "cnv_score_key": cnv_score_col,
        "n_cnv_clusters": int(adata.obs["cnv_leiden"].nunique()) if "cnv_leiden" in adata.obs else 0,
        **fallback,
    }


def run_numbat(adata, *, reference_key: str | None = None, reference_cat: list[str] | None = None,
               genome: str = METHOD_PARAM_DEFAULTS["numbat"]["genome"],
               max_entropy: float = METHOD_PARAM_DEFAULTS["numbat"]["max_entropy"],
               min_llr: float = METHOD_PARAM_DEFAULTS["numbat"]["min_llr"],
               min_cells: int = METHOD_PARAM_DEFAULTS["numbat"]["min_cells"],
               ncores: int = METHOD_PARAM_DEFAULTS["numbat"]["ncores"],
               allele_counts=None, random_state: int = 0) -> dict:
    """Haplotype-aware CNV inference via R Numbat subprocess.

    Uses raw integer UMI counts from ``adata.layers["counts"]`` — Numbat's
    model explicitly requires a gene-by-cell integer UMI count matrix as its
    expression input.  Do NOT pass log-normalized data.

    Additionally requires:
      - ``adata.obsm["allele_counts"]``: phased allele counts DataFrame
        (from ``pileup_and_phase.R``) with columns cell/snp_id/CHROM/POS/AD/DP/GT/gene
      - Optional ``lambdas_ref``: gene x cell_type normalized reference expression

    Counts are exchanged with R as a genes-by-cells Matrix Market file.
    """
    import tempfile
    from scipy.io import mmwrite
    from pathlib import Path
    from skills._sdk.deps import validate_r_environment
    from skills._sdk.r_script_runner import RScriptRunner
    from skills._sdk.r_utils import read_r_result_csv

    validate_r_environment(required_r_packages=["numbat", "Matrix"])

    if not reference_key or not reference_cat:
        raise ValueError(
            "Current OmicsClaw Numbat wrapper requires --reference-key and "
            "--reference-cat to build diploid reference expression profiles."
        )

    if genome not in VALID_NUMBAT_GENOMES:
        raise ValueError(f"Unsupported Numbat genome '{genome}'. Choose from: {VALID_NUMBAT_GENOMES}")

    allele_df = _get_allele_counts_df(adata, allele_counts)
    if "counts" not in adata.layers:
        raise ValueError("Numbat requires raw integer layers['counts']")
    export_X = adata.layers["counts"]
    scripts_dir = Path(__file__).resolve().parents[1] / "spatial-cnv" / "rscripts"
    runner = RScriptRunner(scripts_dir=scripts_dir)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_numbat_") as tmpdir:
        tmpdir = Path(tmpdir)
        allele_path = tmpdir / "allele_counts.csv"
        mmwrite(tmpdir / "counts.mtx", sparse.coo_matrix(export_X.T))
        pd.Series(adata.obs_names).to_csv(tmpdir / "barcodes.tsv", sep="\t", index=False, header=False)
        pd.Series(adata.var_names).to_csv(tmpdir / "features.tsv", sep="\t", index=False, header=False)
        adata.obs.to_csv(tmpdir / "obs.csv", index_label="cell")
        allele_df.to_csv(allele_path, index=False)

        output_dir = tmpdir / "output"
        output_dir.mkdir()

        args = [
            str(tmpdir),
            str(output_dir),
            str(allele_path),
            reference_key or "",
            ",".join(reference_cat or []),
            genome,
            str(max_entropy),
            str(min_llr),
            str(min_cells),
            str(ncores),
            str(random_state),
        ]

        logger.info("Spawning external R process for Numbat...")
        runner.run_script(
            "numbat.R",
            args=args,
            expected_outputs=["numbat_results.csv", "numbat_clone_post.csv"],
            output_dir=output_dir,
        )

        result_df = read_r_result_csv(output_dir / "numbat_results.csv", index_col=None)
        clone_post_df = read_r_result_csv(output_dir / "numbat_clone_post.csv", index_col=None)

        # Store results back into original adata safely
        if result_df is not None and not result_df.empty:
            adata.uns["numbat_calls"] = result_df.to_dict("records")
            logger.info("Successfully joined %d Numbat CNV segment calls", len(result_df))
        else:
            logger.warning("Numbat returned empty CNV calls")

        p_cnv = None
        if clone_post_df is not None and not clone_post_df.empty:
            adata.uns["numbat_clone_post"] = clone_post_df.to_dict("records")
            cell_col = next((c for c in ("cell", "barcode", "cell_id") if c in clone_post_df.columns), None)
            if cell_col is not None:
                clone_post_df = clone_post_df.copy()
                clone_post_df[cell_col] = clone_post_df[cell_col].astype(str)
                clone_post_df = clone_post_df.set_index(cell_col)

                if "p_cnv" in clone_post_df.columns:
                    p_cnv = clone_post_df["p_cnv"].reindex(adata.obs_names)
                    adata.obs["numbat_p_cnv"] = pd.to_numeric(p_cnv, errors="coerce")
                if "clone_opt" in clone_post_df.columns:
                    adata.obs["numbat_clone"] = clone_post_df["clone_opt"].reindex(adata.obs_names)
                elif "clone" in clone_post_df.columns:
                    adata.obs["numbat_clone"] = clone_post_df["clone"].reindex(adata.obs_names)
                if "entropy" in clone_post_df.columns:
                    adata.obs["numbat_entropy"] = pd.to_numeric(
                        clone_post_df["entropy"].reindex(adata.obs_names),
                        errors="coerce",
                    )

        if p_cnv is not None and not p_cnv.dropna().empty:
            mean_score = float(p_cnv.dropna().mean())
            high_cnv_pct = float((p_cnv.dropna() > 0.5).mean() * 100)
        else:
            mean_score = 0.0
            high_cnv_pct = 0.0

    return {
        "method": "numbat",
        "n_genes": adata.n_vars,
        "mean_cnv_score": float(f"{mean_score:.4f}"),
        "high_cnv_fraction_pct": float(f"{high_cnv_pct:.2f}"),
        "n_cnv_calls": len(result_df) if result_df is not None and not result_df.empty else 0,
        "cnv_score_key": "numbat_p_cnv" if "numbat_p_cnv" in adata.obs.columns else None,
    }


def run_cnv(adata, *, method: str = "infercnvpy", reference_key: str | None = None,
            reference_cat: list[str] | str | None = None, window_size: int = 100, step: int = 10,
            infercnv_dynamic_threshold: float | None = METHOD_PARAM_DEFAULTS["infercnvpy"]["dynamic_threshold"],
            infercnv_lfc_clip: float = METHOD_PARAM_DEFAULTS["infercnvpy"]["lfc_clip"],
            infercnv_exclude_chromosomes=None,
            infercnv_chunksize: int = METHOD_PARAM_DEFAULTS["infercnvpy"]["chunksize"],
            infercnv_n_jobs: int | None = METHOD_PARAM_DEFAULTS["infercnvpy"]["n_jobs"],
            numbat_genome: str = METHOD_PARAM_DEFAULTS["numbat"]["genome"],
            numbat_max_entropy: float = METHOD_PARAM_DEFAULTS["numbat"]["max_entropy"],
            numbat_min_llr: float = METHOD_PARAM_DEFAULTS["numbat"]["min_llr"],
            numbat_min_cells: int = METHOD_PARAM_DEFAULTS["numbat"]["min_cells"],
            numbat_ncores: int = METHOD_PARAM_DEFAULTS["numbat"]["ncores"],
            random_state: int = 0, numbat_allele_counts=None) -> dict:
    """Run CNV inference. Returns summary dict.

    Input matrix is selected per-method:
      - infercnvpy: adata.X (log-normalized)
      - numbat: adata.layers["counts"] (raw integer UMI counts)
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown CNV method '{method}'. Choose from: {SUPPORTED_METHODS}")

    # Safely cast string to list for the reference categories to prevent iteration bugs
    if isinstance(reference_cat, str):
        reference_cat = [reference_cat]
    reference_cat = reference_cat or []

    validate_reference(adata, reference_key, reference_cat)

    logger.info("Starting CNV inference workflow using method '%s' (%d cells, %d genes)...", method, adata.n_obs, adata.n_vars)

    if method == "numbat":
        result = run_numbat(
            adata,
            reference_key=reference_key,
            reference_cat=reference_cat,
            genome=numbat_genome,
            max_entropy=numbat_max_entropy,
            min_llr=numbat_min_llr,
            min_cells=numbat_min_cells,
            ncores=numbat_ncores,
            allele_counts=numbat_allele_counts,
            random_state=random_state,
        )
    elif method == "infercnvpy":
        result = run_infercnvpy(
            adata,
            reference_key=reference_key,
            reference_cat=reference_cat,
            window_size=window_size,
            step=step,
            dynamic_threshold=infercnv_dynamic_threshold,
            lfc_clip=infercnv_lfc_clip,
            exclude_chromosomes=infercnv_exclude_chromosomes,
            chunksize=infercnv_chunksize,
            n_jobs=infercnv_n_jobs,
            random_state=random_state,
        )
    else:
        raise NotImplementedError(f"Handler for method '{method}' is not implemented.")

    return {"n_cells": adata.n_obs, "n_genes": adata.n_vars, **result}
