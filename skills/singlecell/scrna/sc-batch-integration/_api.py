"""Batch-correct representations without choosing a clustering or UMAP workflow."""

from __future__ import annotations

import importlib
import json
import logging
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc

from skills.singlecell._lib import integration as sc_integration_utils
from skills.singlecell._lib.adata_utils import ensure_pca
from skills._sdk.deps import validate_r_environment
from skills._sdk.r_script_runner import RScriptRunner
from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR

__all__ = ["integrate", "run_info", "integration_metrics", "batch_mixing_table", "batch_sizes_table", "batch_sizes_figure"]

logger = logging.getLogger(__name__)
_RUN_KEY = "omicsclaw_sc_batch_integration_run"
_METHODS = ("harmony", "scvi", "scanvi", "bbknn", "scanorama", "simba", "fastmnn", "seurat_cca", "seurat_rpca")


def _backend(module: str, package: str):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ImportError(
            f"This integration method needs {package}; ask install_skill_deps "
            f"for sc-batch-integration and run with its overlay interpreter."
        ) from exc


def integrate(
    adata,
    *,
    method: str = "harmony",
    batch_key: str = "batch",
    harmony_theta: float = 2.0,
    n_pcs: int = 50,
    n_latent: int = 30,
    n_epochs: int | None = None,
    use_gpu: bool = True,
    labels_key: str | None = None,
    bbknn_neighbors_within_batch: int = 3,
    scanorama_knn: int = 20,
    integration_features: int = 2000,
    integration_pcs: int = 30,
    simba_n_top_genes: int = 3000,
    simba_n_components: int = 15,
    simba_k: int = 15,
    simba_num_workers: int = 4,
    random_state: int = 0,
):
    """Integrate batches and return AnnData with a corrected representation.

    ``harmony`` reads log-normalised expression and batch labels, writes
    ``obsm['X_harmony']`` and preserves cells and genes. It recomputes PCA on
    ordinary inputs; when ``n_pcs`` exceeds the small input's rank, it reuses
    an existing PCA or computes the largest valid PCA. No neighbours or UMAP
    are computed. Diagnostics are available through :func:`run_info`.

    :param method: ``harmony`` (default), ``scvi``, ``scanvi``, ``bbknn``,
        ``scanorama``, ``simba``, ``fastmnn``, ``seurat_cca`` or ``seurat_rpca``.
        BBKNN writes its batch-balanced neighbour graph, not a new embedding.
    :param batch_key: Batch column in ``obs``; default ``batch``.
    :param harmony_theta: Harmony diversity penalty; default 2.0.
    :param n_pcs: Requested Harmony components; default 50.
    :param n_latent: scVI/scANVI latent dimensions; default 30.
    :param n_epochs: Training epochs; None uses 400 for scVI, 200 for scANVI.
    :param use_gpu: Request a GPU for scVI/scANVI; default True, CPU if unavailable.
    :param labels_key: scANVI labels; None searches cell_type/leiden/louvain/
        seurat_clusters. With no labels it falls back to scVI and records why.
    :param bbknn_neighbors_within_batch: BBKNN neighbours per batch; default 3.
    :param scanorama_knn: Scanorama matching neighbours; default 20.
    :param integration_features: R integration variable genes; default 2000.
    :param integration_pcs: R integration components; default 30.
    :param simba_n_top_genes: SIMBA variable genes; default 3000.
    :param simba_n_components: SIMBA inter-batch components; default 15.
    :param simba_k: SIMBA inter-batch neighbours; default 15.
    :param simba_num_workers: SIMBA training workers; default 4.
    :param random_state: Backend seed; default 0.
        Passed to Harmony, Scanorama and scVI/scANVI. SIMBA and the retained
        R bridge do not expose this seed. SIMBA runs in a temporary working
        directory; do not call it concurrently from multiple threads.
    :returns: AnnData, modified in place for Python methods except SIMBA.
        SIMBA and R methods can return a cell-subset copy. scVI/scANVI require
        raw counts in ``layers['counts']``; other Python methods use ``X``.
    :raises ValueError: The method, batch column or PCA dimensions are invalid.
    :raises ImportError: The chosen optional backend is unavailable.
    """
    if method not in _METHODS:
        raise ValueError(f"Unknown integration method: {method}")
    if batch_key not in adata.obs:
        raise ValueError(f"Batch column {batch_key!r} is absent from adata.obs")
    if method == "harmony":
        _backend("harmonypy", "harmonypy")
    sc_integration_utils.setup_for_integration(adata, batch_key=batch_key, inplace=True)
    requested_method = method
    fallback_reason = None
    if method == "harmony":
        if n_pcs < 1:
            raise ValueError("n_pcs must be positive")
        n_features = int(adata.var["highly_variable"].sum()) if "highly_variable" in adata.var else adata.n_vars
        rank_limit = min(adata.n_obs, n_features)
        use_pca = n_pcs < rank_limit
        if not use_pca and "X_pca" not in adata.obsm:
            if rank_limit < 2:
                raise ValueError("Harmony requires at least two cells and two variable genes")
            sc.tl.pca(adata, n_comps=rank_limit - 1, random_state=random_state)
        adata = sc_integration_utils.run_harmony_integration(
            adata, batch_key=batch_key, theta=harmony_theta, n_pcs=n_pcs,
            use_pca=use_pca, random_state=random_state,
        )
    elif method in {"scvi", "scanvi"}:
        backend = _backend("scvi", "scvi-tools")
        backend.settings.seed = random_state
        labels_key = labels_key or _preferred_label_key(adata)
        if method == "scanvi" and labels_key is None:
            method = "scvi"
            fallback_reason = "scanvi requires existing labels in adata.obs such as 'cell_type' or 'leiden'"
            logger.warning("scANVI requires labels; falling back to scVI latent integration")
        kwargs = dict(batch_key=batch_key, n_latent=n_latent, use_gpu=use_gpu, random_state=random_state)
        if method == "scanvi":
            adata = sc_integration_utils.run_scanvi_integration(adata, labels_key=labels_key, max_epochs=n_epochs or 200, **kwargs)
        else:
            adata = sc_integration_utils.run_scvi_integration(adata, max_epochs=n_epochs or 400, **kwargs)
    elif method == "bbknn":
        backend = _backend("bbknn", "bbknn")
        ensure_pca(adata)
        backend.bbknn(adata, batch_key=batch_key, neighbors_within_batch=bbknn_neighbors_within_batch)
    elif method == "scanorama":
        _integrate_scanorama(adata, batch_key=batch_key, knn=scanorama_knn, random_state=random_state)
    elif method == "simba":
        previous = Path.cwd()
        with tempfile.TemporaryDirectory(prefix="omicsclaw_simba_") as scratch:
            try:
                os.chdir(scratch)
                adata, _ = _integrate_simba(adata, batch_key=batch_key, n_top_genes=simba_n_top_genes,
                    n_components=simba_n_components, k=simba_k, num_workers=simba_num_workers)
            finally:
                os.chdir(previous)
    else:
        adata, _, legacy_umap = _integrate_r_method(adata, method=method, batch_key=batch_key,
            n_features=integration_features, n_pcs=integration_pcs)
        if legacy_umap is not None:
            adata.uns["_omicsclaw_legacy_integration_umap"] = np.asarray(legacy_umap)
    key = "X_pca" if method == "bbknn" else f"X_{method}"
    summary = {"method": method, "embedding_key": key, "n_batches": int(adata.obs[batch_key].nunique()),
        "requested_method": requested_method, "executed_method": method,
        "fallback_used": requested_method != method, "n_cells": int(adata.n_obs),
        "recommended_next_skill": "sc-clustering", "recommended_use_rep": key}
    if fallback_reason:
        summary["fallback_reason"] = fallback_reason
    adata.uns[_RUN_KEY] = json.dumps({"summary": summary, "random_state": random_state})
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Return integration diagnostics; set ``keep=False`` to remove them from ``uns``."""
    raw = adata.uns.get(_RUN_KEY, "{}") if keep else adata.uns.pop(_RUN_KEY, "{}")
    return json.loads(raw)


def batch_sizes_figure(adata, *, batch_key: str = "batch"):
    """Return a Figure of cell counts per batch; the caller owns saving and closing it."""
    import matplotlib.pyplot as plt

    table = batch_sizes_table(adata, batch_key=batch_key)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(table[batch_key], table["n_cells"])
    ax.set(xlabel=batch_key, ylabel="Cells")
    fig.tight_layout()
    return fig


def _integrate_simba(adata, batch_key="batch", **kwargs):
    """SIMBA batch integration via graph embedding and PBG training.

    SIMBA learns a unified graph representation across batches using
    PyTorch-BigGraph (PBG) and produces a corrected low-dimensional
    embedding in ``adata.obsm['X_simba']``.

    Requires the ``simba`` Python package.
    """
    si = _backend("simba", "simba-bio")

    n_top_genes = int(kwargs.get("n_top_genes", 3000))
    n_components = int(kwargs.get("n_components", 15))
    k = int(kwargs.get("k", 15))
    num_workers = int(kwargs.get("num_workers", 4))

    logger.info("Running SIMBA integration on %d batches", adata.obs[batch_key].nunique())

    # Ensure batch column is categorical
    adata.obs[batch_key] = adata.obs[batch_key].astype("category")
    batches = adata.obs[batch_key].cat.categories.tolist()

    # Per-batch preprocessing
    adata_dict = {}
    for batch in batches:
        batch_adata = adata[adata.obs[batch_key] == batch].copy()
        si.pp.filter_genes(batch_adata, min_n_cells=3)
        si.pp.cal_qc_rna(batch_adata)
        si.pp.normalize(batch_adata, method="lib_size")
        si.pp.log_transform(batch_adata)
        si.pp.select_variable_genes(batch_adata, n_top_genes=n_top_genes)
        si.tl.discretize(batch_adata, n_bins=5)
        adata_dict[batch] = batch_adata

    # Find largest batch as reference
    batch_sizes = {b: adata_dict[b].n_obs for b in batches}
    ref_batch = max(batch_sizes, key=batch_sizes.get)

    # Infer inter-batch edges
    edge_dict = {}
    for batch in batches:
        if batch == ref_batch:
            continue
        edge_dict[batch] = si.tl.infer_edges(
            adata_dict[ref_batch], adata_dict[batch],
            n_components=n_components, k=k,
        )

    # Generate graph
    si.tl.gen_graph(
        list_CG=[adata_dict[b] for b in batches],
        list_CC=[edge_dict[b] for b in batches if b != ref_batch],
        copy=False,
        dirname="graph0",
    )

    # Train PBG model
    dict_config = si.settings.pbg_params.copy()
    dict_config["workers"] = num_workers
    si.tl.pbg_train(pbg_params=dict_config, auto_wd=True, save_wd=True, output="model")

    # Load and embed
    si.load_graph_stats()
    si.load_pbg_config()
    dict_adata = si.read_embedding()

    # Merge embeddings
    dict_adata2 = {k: v for k, v in dict_adata.items() if k != "G"}
    embed_sizes = {k: v.shape[0] for k, v in dict_adata2.items()}
    max_label = max(embed_sizes, key=embed_sizes.get)
    adata_ref = dict_adata2[max_label]
    list_query = [v for k, v in dict_adata2.items() if k != max_label]
    adata_all = si.tl.embed(adata_ref=adata_ref, list_adata_query=list_query, use_precomputed=False)

    # Map embeddings back
    cell_idx = [c for c in adata_all.obs.index if c in adata.obs.index]
    adata = adata[cell_idx].copy()
    adata.obsm["X_simba"] = adata_all[cell_idx].to_df().values

    return adata, {"method": "simba", "embedding_key": "X_simba", "n_batches": int(adata.obs[batch_key].nunique())}


def _integrate_scanorama(adata, batch_key="batch", **kwargs):
    scanorama = _backend("scanorama", "scanorama")

    logger.info("Running Scanorama on %d batches", adata.obs[batch_key].nunique())
    batches = []
    for batch in adata.obs[batch_key].unique():
        batches.append(adata[adata.obs[batch_key] == batch].copy())
    corrected = scanorama.correct_scanpy(
        batches,
        return_dimred=True,
        seed=int(kwargs.get("random_state", 0)),
        knn=int(kwargs.get("knn", 20)),
    )
    embedding_frames = []
    for corrected_batch in corrected:
        embedding = corrected_batch.obsm.get("X_scanorama")
        if embedding is None:
            raise RuntimeError("Scanorama did not produce 'X_scanorama' embeddings")
        frame = pd.DataFrame(embedding, index=corrected_batch.obs_names)
        embedding_frames.append(frame)
    combined = pd.concat(embedding_frames, axis=0)
    combined = combined.loc[adata.obs_names]
    adata.obsm["X_scanorama"] = combined.to_numpy(dtype=float)
    return {"method": "scanorama", "embedding_key": "X_scanorama", "n_batches": int(adata.obs[batch_key].nunique())}


def _build_r_integration_export_adata(adata):
    if "counts" in adata.layers:
        matrix = adata.layers["counts"]
    elif adata.raw is not None and adata.raw.shape == adata.shape:
        matrix = adata.raw.X
    else:
        matrix = adata.X
    export = sc.AnnData(X=matrix.copy(), obs=adata.obs.copy(), var=adata.var.copy())
    export.obs_names = adata.obs_names.copy()
    export.var_names = adata.var_names.copy()
    return export


def _integrate_r_method(adata, *, method: str, batch_key: str, n_features: int = 2000, n_pcs: int = 30):
    if method == "fastmnn":
        required_packages = ["batchelor", "SingleCellExperiment", "zellkonverter"]
    else:
        required_packages = ["Seurat", "SingleCellExperiment", "zellkonverter"]
    validate_r_environment(required_r_packages=required_packages)
    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    export = _build_r_integration_export_adata(adata)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_sc_integrate_r_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        export.write_h5ad(input_h5ad)
        expected = ["embedding.csv", "obs.csv"] if method == "fastmnn" else ["embedding.csv", "umap.csv", "obs.csv"]
        runner.run_script(
            "sc_seurat_integrate.R",
            args=[str(input_h5ad), str(output_dir), method, batch_key, str(n_features), str(n_pcs)],
            expected_outputs=expected,
            output_dir=output_dir,
        )
        embedding = pd.read_csv(output_dir / "embedding.csv", index_col=0)
        obs_df = pd.read_csv(output_dir / "obs.csv", index_col=0)
        obs_df.index = obs_df.index.astype(str)
        ordered = [cell for cell in adata.obs_names if str(cell) in obs_df.index and str(cell) in embedding.index.astype(str)]
        if not ordered:
            raise RuntimeError(f"R integration method '{method}' returned no overlapping cells")
        embedding.index = embedding.index.astype(str)
        adata = adata[ordered].copy()
        adata.obs = adata.obs.join(obs_df, how="left", rsuffix="_r")
        key = f"X_{method}"
        adata.obsm[key] = embedding.loc[ordered].to_numpy(dtype=float)
        legacy_umap = None
        if method != "fastmnn":
            umap_df = pd.read_csv(output_dir / "umap.csv", index_col=0)
            umap_df.index = umap_df.index.astype(str)
            legacy_umap = umap_df.loc[ordered].to_numpy(dtype=float).tolist()
        return adata, {"method": method, "embedding_key": key, "n_batches": int(adata.obs[batch_key].nunique())}, legacy_umap


def _preferred_label_key(adata) -> str | None:
    for candidate in ("cell_type", "leiden", "louvain", "seurat_clusters"):
        if candidate in adata.obs.columns:
            return candidate
    return None


def batch_sizes_table(adata, *, batch_key: str = "batch") -> pd.DataFrame:
    """Return batch labels and cell counts, largest first."""
    return (
        adata.obs[batch_key]
        .astype(str)
        .value_counts()
        .rename_axis(batch_key)
        .reset_index(name="n_cells")
        .sort_values("n_cells", ascending=False)
        .reset_index(drop=True)
    )


def batch_mixing_table(adata, *, batch_key: str = "batch", label_key: str | None = None) -> pd.DataFrame:
    """Return each label's fraction of cells from each batch; empty without labels."""
    label_key = label_key or _preferred_label_key(adata)
    if not label_key or label_key not in adata.obs.columns:
        return pd.DataFrame()
    mix = pd.crosstab(
        adata.obs[label_key].astype(str),
        adata.obs[batch_key].astype(str),
        normalize="index",
    )
    mix.index.name = label_key
    return mix.reset_index()


def integration_metrics(adata, *, batch_key: str = "batch", label_key: str | None = None, embedding_key: str = "X_harmony") -> pd.DataFrame:
    """Return LISI and ASW diagnostics; unavailable metrics are logged and omitted.

    LISI values are also attached to ``obs["ilisi"]`` and, with labels,
    ``obs["clisi"]``. The corrected embedding and batch column must exist.
    """
    label_key = label_key or _preferred_label_key(adata)
    metrics = {
        "embedding_key": embedding_key,
        "n_batches": int(adata.obs[batch_key].nunique()),
    }
    if label_key and label_key in adata.obs.columns:
        metrics["label_key"] = label_key
        metrics["n_labels"] = int(adata.obs[label_key].nunique())
    try:
        lisi_df = sc_integration_utils.compute_lisi_scores(
            adata,
            batch_key=batch_key,
            label_key=label_key if label_key in adata.obs.columns else None,
            use_rep=embedding_key,
            verbose=False,
        )
        adata.obs["ilisi"] = lisi_df["ilisi"].values
        metrics["mean_ilisi"] = float(lisi_df["ilisi"].mean())
        metrics["median_ilisi"] = float(lisi_df["ilisi"].median())
        if "clisi" in lisi_df.columns:
            adata.obs["clisi"] = lisi_df["clisi"].values
            metrics["mean_clisi"] = float(lisi_df["clisi"].mean())
            metrics["median_clisi"] = float(lisi_df["clisi"].median())
    except Exception as exc:
        logger.warning("LISI diagnostics unavailable: %s", exc)

    try:
        if not label_key or label_key not in adata.obs.columns:
            raise ValueError("No stable label column available yet; skip label-based ASW diagnostics.")
        asw = sc_integration_utils.compute_asw_scores(
            adata,
            batch_key=batch_key,
            label_key=label_key,
            use_rep=embedding_key,
            verbose=False,
        )
        metrics["batch_asw"] = float(asw["batch_asw"])
        metrics["celltype_asw"] = float(asw["celltype_asw"])
    except Exception as exc:
        logger.warning("ASW diagnostics unavailable: %s", exc)

    return pd.DataFrame([metrics])
