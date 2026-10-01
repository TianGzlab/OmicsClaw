"""sc-preprocessing's function library: filter, normalise, select variable genes and run PCA.

In a step: ``pre = load_skill("sc-preprocessing")``. The functions compute and
return objects; they read and write no files. The ``seurat`` and
``sctransform`` methods run R through ``Rscript`` and need the Seurat stack.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc

from skills._sdk.deps import validate_r_environment
from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR
from skills._sdk.r_script_runner import RScriptRunner
from skills.singlecell._lib import dimred as sc_dimred_utils
from skills.singlecell._lib import preprocessing as sc_preproc_utils
from skills.singlecell._lib import qc as sc_qc_utils
from skills.singlecell._lib.adata_utils import (
    canonicalize_singlecell_adata,
    infer_qc_species,
    propagate_singlecell_contracts,
)

__all__ = [
    "preprocess",
    "run_info",
    "hvg_table",
    "pca_variance_table",
    "pca_embedding_table",
    "qc_metrics_table",
    "pca_variance_figure",
]

logger = logging.getLogger(__name__)

METHODS = ("scanpy", "pearson_residuals", "seurat", "sctransform")
_RUN_KEY = "omicsclaw_sc_preprocessing_run"


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def preprocess(
    adata,
    *,
    method: str = "scanpy",
    min_genes: int = 200,
    min_cells: int = 3,
    max_mt_pct: float = 20.0,
    n_top_hvg: int | None = None,
    n_pcs: int = 50,
    normalization_target_sum: float = 10000.0,
    scanpy_hvg_flavor: str = "seurat",
    pearson_hvg_flavor: str = "seurat_v3",
    pearson_theta: float = 100.0,
    seurat_normalize_method: str = "LogNormalize",
    seurat_scale_factor: float = 10000.0,
    seurat_hvg_method: str = "vst",
    sctransform_regress_mt: bool = True,
    remove_doublets: bool = True,
    doublet_score_threshold: float = 0.25,
    preserve_var_names: bool = False,
):
    """Filter cells and genes, normalise, select highly variable genes and run PCA.

    The input is first brought into the OmicsClaw scRNA contract (counts in
    ``layers['counts']``, a counts snapshot in ``raw``) and QC metrics are added
    when missing. Cells and genes are then filtered by the thresholds below,
    and doublets are dropped when ``predicted_doublet`` or ``doublet_score``
    from sc-doublet-detection are in ``obs``. Finally the chosen method
    normalises ``X``, flags ``var['highly_variable']`` and writes
    ``obsm['X_pca']``. What was filtered is recorded for :func:`run_info`.

    :param method: ``"scanpy"`` (normalize_total, log1p, HVG, PCA; the default),
        ``"pearson_residuals"`` (analytic Pearson residuals for HVG and PCA; ``X``
        stays log-normalised), ``"seurat"`` (Seurat LogNormalize in R) or
        ``"sctransform"`` (Seurat SCTransform in R).
    :param min_genes: Drop cells with fewer detected genes. Default 200, the
        scanpy and Seurat tutorial value; lower it for low-depth data.
    :param min_cells: Drop genes detected in fewer cells. Default 3, the tutorial value.
    :param max_mt_pct: Drop cells above this mitochondrial percentage. Default 20.0,
        a permissive threshold; PBMC data usually uses 5 to 10. Agree it with the user.
    :param n_top_hvg: Number of highly variable genes. Default ``None``: 3000 for
        ``sctransform``, 2000 for the other methods (their tutorials' values).
    :param n_pcs: Principal components to compute. Default 50.
    :param normalization_target_sum: Counts per cell after ``normalize_total``
        (``scanpy`` only). Default 10000.
    :param scanpy_hvg_flavor: HVG flavor for ``scanpy``: ``"seurat"`` (default),
        ``"cell_ranger"`` or ``"seurat_v3"``.
    :param pearson_hvg_flavor: HVG flavor for ``pearson_residuals``. Default ``"seurat_v3"``.
    :param pearson_theta: Overdispersion for Pearson residuals. Default 100, scanpy's default.
    :param seurat_normalize_method: Seurat ``NormalizeData`` method. Default ``"LogNormalize"``.
    :param seurat_scale_factor: Seurat scale factor. Default 10000.
    :param seurat_hvg_method: Seurat ``FindVariableFeatures`` method. Default ``"vst"``.
    :param sctransform_regress_mt: Regress out mitochondrial percentage in SCTransform. Default ``True``.
    :param remove_doublets: Drop cells flagged as doublets when the flags are present. Default ``True``.
    :param doublet_score_threshold: Score above which a cell counts as a doublet when only
        ``doublet_score`` is present. Default 0.25.
    :param preserve_var_names: Keep the input's gene identifiers instead of the
        symbols chosen during standardisation. Default ``False``.
    :returns: A new AnnData: filtered, normalised ``X``, ``layers['counts']``, ``raw``
        counts snapshot, ``var['highly_variable']``, ``obsm['X_pca']``, ``uns['pca']``.
    :raises ValueError: an unknown method, or input with no count-like matrix.
    :raises RuntimeError: the R methods fail, or their R packages are missing.
    """
    if method not in METHODS:
        raise ValueError(f"unknown preprocessing method {method!r}; choose one of {', '.join(METHODS)}")
    if n_top_hvg is None:
        n_top_hvg = 3000 if method == "sctransform" else 2000
    effective = {
        "method": method,
        "min_genes": min_genes,
        "min_cells": min_cells,
        "max_mt_pct": max_mt_pct,
        "n_top_hvg": n_top_hvg,
        "n_pcs": n_pcs,
        "remove_doublets": remove_doublets,
        "doublet_score_threshold": doublet_score_threshold,
        "preserve_var_names": preserve_var_names,
    }
    adata, filter_summary, _filter_params, _input_contract = _prepare_input(adata, effective_params=effective)
    if method == "scanpy":
        adata = _scanpy_workflow(
            adata,
            n_top_hvg=int(n_top_hvg),
            n_pcs=int(n_pcs),
            normalization_target_sum=float(normalization_target_sum),
            scanpy_hvg_flavor=str(scanpy_hvg_flavor),
        )
    elif method == "pearson_residuals":
        adata = _pearson_workflow(
            adata,
            n_top_hvg=int(n_top_hvg),
            n_pcs=int(n_pcs),
            pearson_hvg_flavor=str(pearson_hvg_flavor),
            pearson_theta=float(pearson_theta),
        )
    else:
        adata = _run_seurat_preprocessing(
            adata,
            workflow=method,
            min_genes=0,
            min_cells=1,
            max_mt_pct=100.0,
            n_top_hvg=int(n_top_hvg),
            n_pcs=int(n_pcs),
            seurat_normalize_method=str(seurat_normalize_method),
            seurat_scale_factor=float(seurat_scale_factor),
            seurat_hvg_method=str(seurat_hvg_method),
            sctransform_regress_mt=bool(sctransform_regress_mt),
        )
    input_contract, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill="sc-preprocessing",
        x_kind="normalized_expression",
        raw_kind="raw_counts_snapshot" if adata.raw is not None else None,
        preprocess_method=method,
    )
    info = {
        "method": method,
        "filter_summary": filter_summary,
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
    }
    adata.uns[_RUN_KEY] = json.dumps(info, default=_json_default)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """What :func:`preprocess` recorded about its run.

    Keys: ``method``; ``filter_summary`` (cells and genes before and after
    filtering, cells removed by each threshold under ``filter_stats``, whether QC
    metrics were reused, and ``input_preparation``: the matrix used as counts,
    gene-name source, warnings and inferred species); ``input_contract``;
    ``matrix_contract``.

    :param keep: Leave the record in ``adata.uns``; ``False`` removes it.
    :returns: The record, or an empty dict when ``preprocess`` has not run on *adata*.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def hvg_table(adata, *, n_top: int = 50) -> pd.DataFrame:
    """The most variable genes with their mean and dispersion statistics.

    :param n_top: How many genes to return, most variable first. Default 50.
    :returns: Column ``gene`` plus whichever of ``means``, ``variances``,
        ``variances_norm``, ``dispersions``, ``dispersions_norm`` the method wrote.
    """
    if "highly_variable" not in adata.var.columns:
        return pd.DataFrame(columns=["gene"])
    hvg_df = adata.var.loc[adata.var["highly_variable"]].copy()
    if hvg_df.empty:
        return pd.DataFrame(columns=["gene"])

    hvg_df["gene"] = hvg_df.index.astype(str)
    sort_col = ""
    for candidate in ("dispersions_norm", "variances_norm", "dispersions", "means"):
        if candidate in hvg_df.columns:
            sort_col = candidate
            break
    if sort_col:
        hvg_df = hvg_df.sort_values(sort_col, ascending=False, na_position="last")

    keep_cols = ["gene"]
    for column in ("means", "variances", "variances_norm", "dispersions", "dispersions_norm"):
        if column in hvg_df.columns:
            keep_cols.append(column)
    return hvg_df.loc[:, keep_cols].head(n_top).reset_index(drop=True)


def pca_variance_table(adata) -> pd.DataFrame:
    """Variance explained by each principal component, to choose how many to keep downstream.

    :returns: Columns ``pc``, ``variance_ratio`` and ``cumulative_variance_ratio``.
    """
    if "pca" not in adata.uns or "variance_ratio" not in adata.uns["pca"]:
        return pd.DataFrame(columns=["pc", "variance_ratio", "cumulative_variance_ratio"])
    variance_ratio = np.asarray(adata.uns["pca"]["variance_ratio"], dtype=float)
    return pd.DataFrame(
        {
            "pc": np.arange(1, len(variance_ratio) + 1),
            "variance_ratio": variance_ratio,
            "cumulative_variance_ratio": np.cumsum(variance_ratio),
        }
    )


def pca_embedding_table(adata, *, n_components: int = 5) -> pd.DataFrame:
    """The first principal-component coordinates of every cell.

    :param n_components: How many components to include. Default 5.
    :returns: Column ``cell_id`` followed by ``PC1``, ``PC2``, ...
    """
    if "X_pca" not in adata.obsm:
        return pd.DataFrame(columns=["cell_id", "PC1", "PC2"])
    coords = np.asarray(adata.obsm["X_pca"])
    n_components = min(n_components, coords.shape[1])
    data = {"cell_id": adata.obs_names.astype(str)}
    for idx in range(n_components):
        data[f"PC{idx + 1}"] = coords[:, idx]
    return pd.DataFrame(data)


def qc_metrics_table(adata) -> pd.DataFrame:
    """The QC metrics of the cells that passed filtering.

    :returns: Column ``cell_id`` followed by whichever of ``n_genes_by_counts``,
        ``total_counts`` and ``pct_counts_mt`` are in ``obs``.
    """
    qc_cols = [column for column in ("n_genes_by_counts", "total_counts", "pct_counts_mt") if column in adata.obs.columns]
    if not qc_cols:
        return pd.DataFrame(columns=["cell_id"])
    qc_df = adata.obs.loc[:, qc_cols].copy()
    qc_df.insert(0, "cell_id", adata.obs_names.astype(str))
    return qc_df.reset_index(drop=True)


def pca_variance_figure(adata, *, n_pcs: int = 50):
    """An elbow plot of the variance ratio per principal component.

    :param n_pcs: How many components to show. Default 50.
    :returns: A matplotlib Figure.
    :raises KeyError: ``uns['pca']`` is missing; run :func:`preprocess` first.
    """
    import matplotlib.pyplot as plt

    ratio = np.asarray(adata.uns["pca"]["variance_ratio"], dtype=float)[:n_pcs]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(np.arange(1, len(ratio) + 1), ratio, marker="o", markersize=3, color="#4c72b0")
    ax.set_xlabel("principal component")
    ax.set_ylabel("variance ratio")
    ax.set_title("PCA variance ratio")
    fig.tight_layout()
    return fig


def _prepare_input(adata, *, effective_params: dict):
    """Canonicalize the input and run shared QC/filter steps before backend-specific normalization."""
    original_var_names = pd.Index(
        [str(value) for value in adata.var_names],
        dtype="object",
        name=adata.var_names.name,
    )
    species = infer_qc_species(adata)
    canonical_adata, prepared_input, input_contract = canonicalize_singlecell_adata(
        adata,
        species=species,
        standardizer_skill="sc-preprocessing",
    )
    had_qc_metrics = {
        "n_genes_by_counts",
        "total_counts",
        "pct_counts_mt",
    }.issubset(set(canonical_adata.obs.columns))
    canonical_adata = sc_qc_utils.ensure_qc_metrics(
        canonical_adata,
        species=species,
        inplace=True,
    )
    if bool(effective_params.get("preserve_var_names", False)):
        if not original_var_names.is_unique:
            raise ValueError(
                "--preserve-var-names requires unique input feature identifiers"
            )
        if len(original_var_names) != canonical_adata.n_vars:
            raise ValueError("feature axis changed during input canonicalization")
        canonical_adata.var_names = original_var_names
        canonical_adata.uns["omicsclaw_input_contract"]["preserved_var_names"] = True
    filtered_adata, filter_summary, filter_params = sc_qc_utils.apply_threshold_filtering(
        canonical_adata,
        min_genes=int(effective_params["min_genes"]),
        min_cells=int(effective_params["min_cells"]),
        max_mt_percent=float(effective_params["max_mt_pct"]),
        filter_doublets=bool(effective_params.get("remove_doublets", True)),
        doublet_score_threshold=float(effective_params.get("doublet_score_threshold", 0.25)),
    )
    filter_summary["qc_metrics_reused"] = bool(had_qc_metrics)
    filter_summary["input_preparation"] = {
        "expression_source": prepared_input.expression_source,
        "gene_name_source": prepared_input.gene_name_source,
        "warnings": prepared_input.warnings,
        "species": species,
    }
    return filtered_adata, filter_summary, filter_params, input_contract


def _scanpy_workflow(
    adata,
    *,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    normalization_target_sum: float = 10000.0,
    scanpy_hvg_flavor: str = "seurat",
):
    """Implementation-aligned Scanpy preprocessing pipeline."""
    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    adata.layers["counts"] = adata.layers["counts"].copy()
    raw_snapshot = adata.copy()
    raw_snapshot.X = adata.layers["counts"].copy()
    adata.raw = raw_snapshot

    adata = sc_preproc_utils.run_standard_normalization(
        adata,
        target_sum=float(normalization_target_sum),
        inplace=True,
    )
    adata = sc_preproc_utils.find_highly_variable_genes(
        adata,
        n_top_genes=n_top_hvg,
        flavor=str(scanpy_hvg_flavor),
        inplace=True,
    )
    adata = sc_dimred_utils.run_pca_analysis(
        adata,
        n_pcs=n_pcs,
        svd_solver="arpack",
        inplace=True,
    )

    return adata


def _pearson_workflow(
    adata,
    *,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    pearson_hvg_flavor: str = "seurat_v3",
    pearson_theta: float = 100.0,
):
    """Scanpy preprocessing pipeline using Pearson residual normalization."""
    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)

    # Keep a conventional log-normalized view as the final public matrix.
    adata_for_raw = adata.copy()
    adata_for_raw = sc_preproc_utils.run_standard_normalization(adata_for_raw, inplace=True)
    lognorm_x = adata_for_raw.X.copy()
    raw_snapshot = adata.copy()
    raw_snapshot.X = adata.layers["counts"].copy()
    adata.raw = raw_snapshot

    adata = sc_preproc_utils.find_highly_variable_genes(
        adata,
        n_top_genes=n_top_hvg,
        flavor=str(pearson_hvg_flavor),
        inplace=True,
    )
    adata = sc_preproc_utils.run_pearson_residuals(
        adata,
        theta=float(pearson_theta),
        inplace=True,
    )
    adata.layers["pearson_residuals"] = adata.X.copy()
    adata = sc_dimred_utils.run_pca_analysis(adata, n_pcs=n_pcs, svd_solver="arpack", inplace=True)
    adata.X = lognorm_x
    return adata


def _choose_counts_matrix(adata):
    """Return the best available raw-count-like matrix for R-backed workflows."""
    if "counts" in adata.layers:
        return adata.layers["counts"]
    if adata.raw is not None and adata.raw.shape == adata.shape:
        return adata.raw.X
    return adata.X


def _build_export_adata(adata):
    """Build an AnnData export where ``X`` contains counts for the R script."""
    export_adata = adata.copy()
    export_adata.obs_names_make_unique()
    export_adata.var_names_make_unique()
    export_adata.X = _choose_counts_matrix(export_adata).copy()
    return export_adata


def _load_seurat_result(
    export_adata,
    *,
    output_dir: Path,
    workflow: str,
    n_pcs: int,
):
    """Load Seurat CSV outputs back into a standard AnnData object."""
    obs_df = pd.read_csv(output_dir / "obs.csv", index_col=0)
    pca_df = pd.read_csv(output_dir / "pca.csv", index_col=0)
    hvg_df = pd.read_csv(output_dir / "hvg.csv")
    norm_df = pd.read_csv(output_dir / "X_norm.csv", index_col=0)

    info = {}
    info_path = output_dir / "info.json"
    if info_path.exists():
        info = json.loads(info_path.read_text(encoding="utf-8"))

    norm_df = norm_df.T
    norm_df.index = norm_df.index.astype(str)
    norm_df.columns = norm_df.columns.astype(str)
    obs_df.index = obs_df.index.astype(str)
    pca_df.index = pca_df.index.astype(str)

    ordered_cells = [cell for cell in norm_df.index if cell in export_adata.obs_names]
    ordered_genes = [gene for gene in norm_df.columns if gene in export_adata.var_names]
    if not ordered_cells or not ordered_genes:
        raise RuntimeError("Seurat preprocessing returned no overlapping cells or genes")

    norm_df = norm_df.loc[ordered_cells, ordered_genes]
    obs_base = export_adata.obs.loc[ordered_cells].copy()
    var_base = export_adata.var.loc[ordered_genes].copy()

    combined_obs = obs_base.join(obs_df, how="left", rsuffix="_seurat")
    if "nFeature_RNA" in combined_obs and "n_genes_by_counts" not in combined_obs:
        combined_obs["n_genes_by_counts"] = pd.to_numeric(combined_obs["nFeature_RNA"], errors="coerce")
    if "nCount_RNA" in combined_obs and "total_counts" not in combined_obs:
        combined_obs["total_counts"] = pd.to_numeric(combined_obs["nCount_RNA"], errors="coerce")
    if "percent.mt" in combined_obs and "pct_counts_mt" not in combined_obs:
        combined_obs["pct_counts_mt"] = pd.to_numeric(combined_obs["percent.mt"], errors="coerce")
    combined_obs["preprocess_method"] = workflow

    hvg_set = set()
    if "gene" in hvg_df.columns:
        hvg_set = {str(gene) for gene in hvg_df["gene"].dropna().astype(str)}
    var_base["highly_variable"] = [gene in hvg_set for gene in var_base.index.astype(str)]

    result = sc.AnnData(X=norm_df.to_numpy(), obs=combined_obs, var=var_base)
    result.layers["counts"] = export_adata[ordered_cells, ordered_genes].X.copy()

    pca_aligned = pca_df.reindex(ordered_cells)
    if pca_aligned.isna().any().any():
        raise RuntimeError("Seurat preprocessing returned PCA rows that do not align with exported cells")
    result.obsm["X_pca"] = pca_aligned.to_numpy(dtype=float)

    if result.obsm["X_pca"].size:
        variance = np.var(result.obsm["X_pca"], axis=0, ddof=1)
        variance = np.clip(variance, a_min=0.0, a_max=None)
        total = float(variance.sum())
        result.uns["pca"] = {
            "variance": variance,
            "variance_ratio": (variance / total) if total > 0 else variance,
        }

    result.uns["seurat_info"] = info
    # Keep the raw-count snapshot in .raw and normalized expression in .X.
    raw_snapshot = result.copy()
    raw_snapshot.X = result.layers["counts"].copy()
    result.raw = raw_snapshot
    return result


def _run_seurat_preprocessing(
    adata,
    *,
    workflow: str,
    min_genes: int = 200,
    min_cells: int = 3,
    max_mt_pct: float = 20.0,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    seurat_normalize_method: str = "LogNormalize",
    seurat_scale_factor: float = 10000.0,
    seurat_hvg_method: str = "vst",
    sctransform_regress_mt: bool = True,
):
    """Run the Seurat / SCTransform preprocessing backend via the shared R script."""
    required_packages = [
        "Seurat",
        "SingleCellExperiment",
        "zellkonverter",
        "rhdf5",
    ]
    if workflow == "sctransform":
        required_packages.append("sctransform")
    validate_r_environment(required_r_packages=required_packages)

    export_adata = _build_export_adata(adata)
    logger.info("Running R-backed %s preprocessing on %d cells x %d genes", workflow, export_adata.n_obs, export_adata.n_vars)

    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_sc_preprocess_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        r_output_dir = tmpdir / "output"
        basilisk_dir = tmpdir / "basilisk"
        r_output_dir.mkdir(parents=True, exist_ok=True)
        basilisk_dir.mkdir(parents=True, exist_ok=True)
        export_adata.write_h5ad(input_h5ad)

        runner.run_script(
            "sc_seurat_preprocess.R",
            args=[
                str(input_h5ad),
                str(r_output_dir),
                workflow,
                str(min_genes),
                str(min_cells),
                str(max_mt_pct),
                str(n_top_hvg),
                str(n_pcs),
                str(seurat_normalize_method),
                str(seurat_scale_factor),
                str(seurat_hvg_method),
                str(bool(sctransform_regress_mt)).upper(),
            ],
            expected_outputs=["obs.csv", "pca.csv", "hvg.csv", "X_norm.csv", "info.json"],
            output_dir=r_output_dir,
            env={"BASILISK_EXTERNAL_DIR": str(basilisk_dir)},
        )

        return _load_seurat_result(
            export_adata,
            output_dir=r_output_dir,
            workflow=workflow,
            n_pcs=n_pcs,
        )
