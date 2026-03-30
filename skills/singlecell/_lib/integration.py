"""Batch integration and integration diagnostics for single-cell analysis.

Combines scVI / scANVI / Harmony integration with LISI and ASW quality
metrics, plus multi-method comparison utilities.

Public API
----------
setup_for_integration
run_scvi_integration
run_scanvi_integration
run_harmony_integration
compute_lisi_scores
compute_asw_scores
plot_integration_metrics
compare_integration_methods
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np
import pandas as pd

from . import dependency_manager as dm

if TYPE_CHECKING:
    from anndata import AnnData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------


def setup_for_integration(
    adata: AnnData,
    batch_key: str,
    highly_variable_genes: bool = True,
    n_top_genes: int = 2000,
    inplace: bool = True,
) -> AnnData | None:
    """Prepare *adata* for batch integration.

    Validates that *batch_key* exists, ensures raw counts are accessible,
    and optionally selects highly-variable genes using ``seurat_v3`` across
    batches.

    Parameters
    ----------
    adata : AnnData
        AnnData object to prepare.
    batch_key : str
        Column in ``adata.obs`` with batch labels.
    highly_variable_genes : bool
        Select HVGs via ``scanpy.pp.highly_variable_genes`` (default ``True``).
    n_top_genes : int
        Number of HVGs to select (default 2000).
    inplace : bool
        Modify *adata* in place.  If ``False``, returns a copy.

    Returns
    -------
    AnnData or None
        The (possibly copied) AnnData, or ``None`` when *inplace* is ``True``.
    """
    import scanpy as sc  # lazy

    if not inplace:
        adata = adata.copy()

    # -- validate batch key --------------------------------------------------
    if batch_key not in adata.obs.columns:
        raise ValueError(f"Batch key '{batch_key}' not found in adata.obs")

    n_batches = adata.obs[batch_key].nunique()
    logger.info(
        "Preparing data for integration: %d cells, %d genes, %d batches (%s)",
        adata.n_obs,
        adata.n_vars,
        n_batches,
        batch_key,
    )

    # -- ensure raw counts ---------------------------------------------------
    if adata.raw is None and "counts" not in adata.layers:
        warnings.warn(
            "No raw counts found (adata.raw / adata.layers['counts']).  "
            "Integration methods require raw counts.  If adata.X already "
            "contains raw counts they will be used as-is.",
            stacklevel=2,
        )

    # -- HVG selection -------------------------------------------------------
    if highly_variable_genes:
        if "highly_variable" not in adata.var.columns:
            logger.info("Computing %d highly variable genes ...", n_top_genes)
            sc.pp.highly_variable_genes(
                adata,
                n_top_genes=n_top_genes,
                batch_key=batch_key,
                flavor="seurat_v3",
                layer="counts" if "counts" in adata.layers else None,
            )

        n_hvgs = int(adata.var["highly_variable"].sum())
        logger.info("Highly variable genes: %d", n_hvgs)

        if n_hvgs < 500:
            warnings.warn(
                f"Only {n_hvgs} HVGs found.  Consider increasing n_top_genes "
                "or setting highly_variable_genes=False.",
                stacklevel=2,
            )

    logger.info("Data preparation complete.")
    return adata


# ---------------------------------------------------------------------------
# Confounding check
# ---------------------------------------------------------------------------

_CANDIDATE_CONDITION_KEYS = [
    "condition",
    "disease",
    "group",
    "treatment",
    "status",
    "diagnosis",
    "phenotype",
]


def _check_batch_condition_confounding(
    adata: AnnData,
    batch_key: str,
    condition_key: str | None = None,
) -> None:
    """Warn when a biological condition has N=1 samples (confounded).

    If *condition_key* is ``None`` the function tries a list of common column
    names.  Silently returns if no condition column is found.
    """
    if condition_key is None:
        for key in _CANDIDATE_CONDITION_KEYS:
            if key in adata.obs.columns:
                condition_key = key
                break
        if condition_key is None:
            return

    if condition_key not in adata.obs.columns:
        return

    batch_condition = adata.obs[[batch_key, condition_key]].drop_duplicates()
    condition_counts = batch_condition[condition_key].value_counts()

    singleton_conditions = condition_counts[condition_counts == 1]
    if len(singleton_conditions) > 0:
        logger.warning("BATCH-CONDITION CONFOUNDING detected:")
        for cond, _count in singleton_conditions.items():
            sample = batch_condition.loc[
                batch_condition[condition_key] == cond, batch_key
            ].values[0]
            logger.warning(
                "  '%s': 1 sample (%s) -- biological signal confounded with batch",
                cond,
                sample,
            )
        logger.warning(
            "  Clustering / annotation remain valid; pseudobulk DE requires "
            ">=2 replicates per condition."
        )
    else:
        min_count = condition_counts.min()
        if min_count < 3:
            logger.info(
                "Some conditions have only %d sample(s). Condition distribution: %s.  "
                "Minimum 3 per condition recommended for pseudobulk DE.",
                min_count,
                dict(condition_counts),
            )


# ---------------------------------------------------------------------------
# scVI
# ---------------------------------------------------------------------------


def run_scvi_integration(
    adata: AnnData,
    batch_key: str,
    condition_key: str | None = None,
    n_latent: int = 30,
    n_layers: int = 2,
    n_hidden: int = 128,
    max_epochs: int = 400,
    early_stopping: bool = True,
    use_gpu: bool = True,
    use_highly_variable: bool = True,
    save_model: str | Path | None = None,
    random_state: int = 0,
) -> AnnData:
    """Run scVI batch integration.

    Learns a low-dimensional latent space while modelling batch effects with a
    deep generative model (negative-binomial likelihood).

    The latent representation is stored in ``adata.obsm['X_scvi']`` and model
    metadata in ``adata.uns['scvi_integration']``.

    Parameters
    ----------
    adata : AnnData
        Must contain raw counts in ``adata.X`` or ``adata.layers['counts']``.
    batch_key : str
        Batch column in ``adata.obs``.
    condition_key : str, optional
        Biological-condition column for confounding check.
    n_latent, n_layers, n_hidden : int
        scVI architecture hyper-parameters.
    max_epochs : int
        Maximum training epochs (default 400).
    early_stopping : bool
        Enable early stopping on validation ELBO (default ``True``).
    use_gpu : bool
        Attempt GPU training (default ``True``; falls back to CPU).
    use_highly_variable : bool
        Subset to HVGs before training (default ``True``).
    save_model : path-like, optional
        Directory to persist the trained model.
    random_state : int
        Seed for reproducibility.

    Returns
    -------
    AnnData
        *adata* with ``obsm['X_scvi']`` added.
    """
    scvi = dm.require("scvi-tools", feature="scVI integration")
    import scanpy as sc  # noqa: F811 – lazy

    logger.info("=== scVI Integration ===")

    _check_batch_condition_confounding(adata, batch_key, condition_key)

    # -- subset to HVGs ------------------------------------------------------
    if use_highly_variable and "highly_variable" in adata.var.columns:
        adata_input = adata[:, adata.var["highly_variable"]].copy()
        logger.info("Using %d highly variable genes", adata_input.n_vars)
    else:
        adata_input = adata.copy()

    # -- setup ----------------------------------------------------------------
    logger.info("Setting up scVI model ...")
    scvi.model.SCVI.setup_anndata(
        adata_input,
        batch_key=batch_key,
        layer="counts" if "counts" in adata_input.layers else None,
    )

    model = scvi.model.SCVI(
        adata_input,
        n_latent=n_latent,
        n_layers=n_layers,
        n_hidden=n_hidden,
        gene_likelihood="nb",
        dropout_rate=0.1,
    )

    logger.info(
        "Architecture: latent=%d, layers=%d, hidden=%d, likelihood=nb",
        n_latent,
        n_layers,
        n_hidden,
    )

    # -- GPU fallback ---------------------------------------------------------
    if use_gpu:
        try:
            import torch

            if not torch.cuda.is_available():
                logger.info("GPU requested but CUDA unavailable -- using CPU.")
                use_gpu = False
        except ImportError:
            logger.info("PyTorch not found -- using CPU.")
            use_gpu = False

    # -- train ----------------------------------------------------------------
    logger.info(
        "Training scVI (max_epochs=%d, early_stopping=%s, gpu=%s) ...",
        max_epochs,
        early_stopping,
        use_gpu,
    )

    model.train(
        max_epochs=max_epochs,
        early_stopping=early_stopping,
        use_gpu=use_gpu,
        check_val_every_n_epoch=10,
        train_size=0.9,
    )

    train_loss = model.history["elbo_train"][1:]
    val_loss = model.history["elbo_validation"]
    logger.info(
        "Training complete: %d epochs, train_loss=%.2f, val_loss=%.2f",
        len(train_loss),
        float(train_loss.iloc[-1]),
        float(val_loss.iloc[-1]),
    )

    # -- latent representation ------------------------------------------------
    latent = model.get_latent_representation()
    adata.obsm["X_scvi"] = latent
    logger.info("Added 'X_scvi' to adata.obsm (shape: %s)", latent.shape)

    # -- persist model --------------------------------------------------------
    if save_model is not None:
        save_path = Path(save_model)
        save_path.mkdir(parents=True, exist_ok=True)
        model.save(save_path, overwrite=True)
        logger.info("Model saved to: %s", save_path)

    # -- store metadata -------------------------------------------------------
    adata.uns["scvi_integration"] = {
        "batch_key": batch_key,
        "n_latent": n_latent,
        "n_layers": n_layers,
        "n_hidden": n_hidden,
        "max_epochs": max_epochs,
        "epochs_trained": len(train_loss),
        "final_train_loss": float(train_loss.iloc[-1]),
        "final_val_loss": float(val_loss.iloc[-1]),
        "use_highly_variable": use_highly_variable,
        "n_genes": adata_input.n_vars,
    }

    logger.info("scVI integration complete.")
    return adata


# ---------------------------------------------------------------------------
# scANVI
# ---------------------------------------------------------------------------


def run_scanvi_integration(
    adata: AnnData,
    batch_key: str,
    labels_key: str,
    unlabeled_category: str = "Unknown",
    from_scvi_model: str | Path | None = None,
    n_latent: int = 30,
    n_layers: int = 2,
    n_hidden: int = 128,
    max_epochs: int = 200,
    use_gpu: bool = True,
    use_highly_variable: bool = True,
    save_model: str | Path | None = None,
    random_state: int = 0,
) -> AnnData:
    """Run scANVI semi-supervised integration.

    Extends scVI by incorporating cell-type labels during training, improving
    integration for rare populations.

    Results are stored in ``adata.obsm['X_scanvi']`` and predicted labels in
    ``adata.obs['scanvi_predictions']``.

    Parameters
    ----------
    adata : AnnData
        Must contain raw counts.
    batch_key : str
        Batch column.
    labels_key : str
        Cell-type label column (may include *unlabeled_category*).
    unlabeled_category : str
        Value in *labels_key* that denotes unlabelled cells (default
        ``"Unknown"``).
    from_scvi_model : path-like, optional
        Path to a pre-trained scVI model directory (recommended).
    n_latent, n_layers, n_hidden, max_epochs : int
        Architecture / training hyper-parameters.
    use_gpu : bool
        Attempt GPU training.
    use_highly_variable : bool
        Subset to HVGs.
    save_model : path-like, optional
        Persist the trained model.
    random_state : int
        Seed.

    Returns
    -------
    AnnData
        *adata* with ``obsm['X_scanvi']`` and ``obs['scanvi_predictions']``.
    """
    scvi = dm.require("scvi-tools", feature="scANVI integration")

    logger.info("=== scANVI Integration ===")

    if labels_key not in adata.obs.columns:
        raise ValueError(f"Labels key '{labels_key}' not found in adata.obs")

    n_labeled = int((adata.obs[labels_key] != unlabeled_category).sum())
    n_unlabeled = int((adata.obs[labels_key] == unlabeled_category).sum())
    n_categories = adata.obs[labels_key].nunique()
    logger.info(
        "Labels: %d labelled (%.1f%%), %d unlabelled, %d categories",
        n_labeled,
        100 * n_labeled / adata.n_obs,
        n_unlabeled,
        n_categories,
    )

    # -- subset to HVGs ------------------------------------------------------
    if use_highly_variable and "highly_variable" in adata.var.columns:
        adata_input = adata[:, adata.var["highly_variable"]].copy()
        logger.info("Using %d highly variable genes", adata_input.n_vars)
    else:
        adata_input = adata.copy()

    layer = "counts" if "counts" in adata_input.layers else None

    # -- build model ----------------------------------------------------------
    if from_scvi_model is not None:
        logger.info("Loading pre-trained scVI model from: %s", from_scvi_model)
        scvi_model = scvi.model.SCVI.load(str(from_scvi_model), adata_input)
        scvi.model.SCANVI.setup_anndata(
            adata_input,
            batch_key=batch_key,
            labels_key=labels_key,
            unlabeled_category=unlabeled_category,
            layer=layer,
        )
        model = scvi.model.SCANVI.from_scvi_model(
            scvi_model,
            unlabeled_category=unlabeled_category,
            labels_key=labels_key,
        )
        logger.info("scANVI initialised from pre-trained scVI model.")
    else:
        logger.info("Training scANVI from scratch (prefer from_scvi_model for better results).")
        scvi.model.SCANVI.setup_anndata(
            adata_input,
            batch_key=batch_key,
            labels_key=labels_key,
            unlabeled_category=unlabeled_category,
            layer=layer,
        )
        model = scvi.model.SCANVI(
            adata_input,
            n_latent=n_latent,
            n_layers=n_layers,
            n_hidden=n_hidden,
            unlabeled_category=unlabeled_category,
        )

    # -- GPU fallback ---------------------------------------------------------
    if use_gpu:
        try:
            import torch

            if not torch.cuda.is_available():
                logger.info("GPU requested but CUDA unavailable -- using CPU.")
                use_gpu = False
        except ImportError:
            logger.info("PyTorch not found -- using CPU.")
            use_gpu = False

    # -- train ----------------------------------------------------------------
    logger.info("Training scANVI (max_epochs=%d, gpu=%s) ...", max_epochs, use_gpu)
    model.train(
        max_epochs=max_epochs,
        use_gpu=use_gpu,
        check_val_every_n_epoch=10,
        train_size=0.9,
    )
    logger.info("Training complete.")

    # -- extract --------------------------------------------------------------
    latent = model.get_latent_representation()
    predictions = model.predict()

    adata.obsm["X_scanvi"] = latent
    adata.obs["scanvi_predictions"] = predictions
    logger.info("Added 'X_scanvi' to obsm (shape: %s) and 'scanvi_predictions' to obs.", latent.shape)

    if n_labeled > 0:
        labeled_mask = adata.obs[labels_key] != unlabeled_category
        accuracy = float(
            (adata.obs.loc[labeled_mask, labels_key] == adata.obs.loc[labeled_mask, "scanvi_predictions"]).mean()
        )
        logger.info("Prediction accuracy on labelled cells: %.1f%%", accuracy * 100)

    # -- persist model --------------------------------------------------------
    if save_model is not None:
        save_path = Path(save_model)
        save_path.mkdir(parents=True, exist_ok=True)
        model.save(save_path, overwrite=True)
        logger.info("Model saved to: %s", save_path)

    # -- store metadata -------------------------------------------------------
    adata.uns["scanvi_integration"] = {
        "batch_key": batch_key,
        "labels_key": labels_key,
        "unlabeled_category": unlabeled_category,
        "n_labeled": n_labeled,
        "n_unlabeled": n_unlabeled,
        "n_categories": n_categories,
        "from_scvi": from_scvi_model is not None,
        "use_highly_variable": use_highly_variable,
        "n_genes": adata_input.n_vars,
    }

    logger.info("scANVI integration complete.")
    return adata


# ---------------------------------------------------------------------------
# Harmony
# ---------------------------------------------------------------------------


def run_harmony_integration(
    adata: AnnData,
    batch_key: str,
    theta: float = 2.0,
    max_iter_harmony: int = 10,
    use_pca: bool = True,
    n_pcs: int = 50,
    random_state: int = 0,
) -> AnnData:
    """Run Harmony integration on PCA space.

    Fast, interpretable batch correction that iteratively clusters and
    corrects the PCA embedding.  No GPU required.

    The corrected embedding is stored in ``adata.obsm['X_harmony']``.

    Parameters
    ----------
    adata : AnnData
        Normalised AnnData (or with PCA already computed).
    batch_key : str
        Batch column.
    theta : float
        Diversity penalty (0 = none, 2 = standard, 4 = aggressive).
    max_iter_harmony : int
        Harmony iteration limit (default 10).
    use_pca : bool
        Recompute PCA before running Harmony (default ``True``).
    n_pcs : int
        Number of principal components (default 50).
    random_state : int
        Seed.

    Returns
    -------
    AnnData
        *adata* with ``obsm['X_harmony']`` added.
    """
    hm = dm.require("harmonypy", feature="Harmony integration")
    import scanpy as sc  # lazy

    logger.info("=== Harmony Integration ===")

    if batch_key not in adata.obs.columns:
        raise ValueError(f"Batch key '{batch_key}' not found in adata.obs")

    n_batches = adata.obs[batch_key].nunique()
    logger.info("Batches: %d (%s), cells: %d", n_batches, batch_key, adata.n_obs)

    # -- PCA ------------------------------------------------------------------
    if use_pca or "X_pca" not in adata.obsm:
        logger.info("Computing PCA (%d components) ...", n_pcs)
        sc.tl.pca(adata, n_comps=n_pcs, random_state=random_state)
    else:
        n_pcs = adata.obsm["X_pca"].shape[1]
        logger.info("Using existing PCA (shape: %s)", adata.obsm["X_pca"].shape)

    # -- Harmony --------------------------------------------------------------
    logger.info("Running Harmony (theta=%.1f, max_iter=%d) ...", theta, max_iter_harmony)

    harmony_out = hm.run_harmony(
        adata.obsm["X_pca"],
        adata.obs,
        batch_key,
        theta=theta,
        max_iter_harmony=max_iter_harmony,
        random_state=random_state,
        verbose=False,
    )

    # harmonypy already returns (n_cells, n_components); do not transpose.
    adata.obsm["X_harmony"] = harmony_out.Z_corr
    logger.info("Added 'X_harmony' to obsm (shape: %s)", adata.obsm["X_harmony"].shape)

    adata.uns["harmony_integration"] = {
        "batch_key": batch_key,
        "theta": theta,
        "max_iter_harmony": max_iter_harmony,
        "n_pcs": n_pcs,
        "n_batches": int(n_batches),
    }

    logger.info("Harmony integration complete.")
    return adata


# ---------------------------------------------------------------------------
# Diagnostics -- LISI
# ---------------------------------------------------------------------------


def compute_lisi_scores(
    adata: AnnData,
    batch_key: str,
    label_key: str | None = None,
    use_rep: str = "X_pca",
    perplexity: float = 30,
    verbose: bool = True,
) -> pd.DataFrame:
    """Compute Local Inverse Simpson's Index (LISI).

    * **iLISI** (batch mixing): 1 = no mixing, *n_batches* = perfect.  Higher
      is better.
    * **cLISI** (cell-type separation): 1 = perfect, *n_types* = worst.
      Lower is better.

    Parameters
    ----------
    adata : AnnData
        Integrated AnnData.
    batch_key : str
        Batch column.
    label_key : str, optional
        Cell-type column.  If ``None`` only iLISI is computed.
    use_rep : str
        ``obsm`` key for the embedding.
    perplexity : float
        Local neighbourhood size (default 30).
    verbose : bool
        Log summary statistics.

    Returns
    -------
    DataFrame
        Columns ``ilisi`` (and ``clisi`` when *label_key* given), indexed by
        ``adata.obs.index``.
    """
    hm = dm.require("harmonypy", feature="LISI computation")
    from harmonypy import compute_lisi

    if verbose:
        logger.info("Computing LISI scores ...")

    for key, name in [(batch_key, "Batch key"), (use_rep, "Representation")]:
        if name == "Batch key" and key not in adata.obs.columns:
            raise ValueError(f"{name} '{key}' not found in adata.obs")
        if name == "Representation" and key not in adata.obsm:
            raise ValueError(f"{name} '{key}' not found in adata.obsm")

    if label_key is not None and label_key not in adata.obs.columns:
        raise ValueError(f"Label key '{label_key}' not found in adata.obs")

    X = adata.obsm[use_rep]

    metadata = adata.obs[[batch_key]].copy()
    if label_key is not None:
        metadata[label_key] = adata.obs[label_key]

    # -- iLISI ----------------------------------------------------------------
    ilisi = compute_lisi(X, metadata, [batch_key], perplexity=perplexity)
    results = pd.DataFrame({"ilisi": ilisi[:, 0]}, index=adata.obs.index)

    if verbose:
        n_batches = adata.obs[batch_key].nunique()
        logger.info(
            "  iLISI  mean=%.2f  median=%.2f  (target=%d)",
            results["ilisi"].mean(),
            results["ilisi"].median(),
            n_batches,
        )

    # -- cLISI ----------------------------------------------------------------
    if label_key is not None:
        clisi = compute_lisi(X, metadata, [label_key], perplexity=perplexity)
        results["clisi"] = clisi[:, 0]
        if verbose:
            logger.info(
                "  cLISI  mean=%.2f  median=%.2f  (target=1.0)",
                results["clisi"].mean(),
                results["clisi"].median(),
            )

    return results


# ---------------------------------------------------------------------------
# Diagnostics -- ASW
# ---------------------------------------------------------------------------


def compute_asw_scores(
    adata: AnnData,
    batch_key: str,
    label_key: str,
    use_rep: str = "X_pca",
    metric: str = "euclidean",
    verbose: bool = True,
) -> dict[str, Any]:
    """Compute Average Silhouette Width (ASW).

    * **Batch ASW**: ~0 is ideal (batches well-mixed).
    * **Cell-type ASW**: >0.5 is good (types well-separated).

    Parameters
    ----------
    adata : AnnData
        Integrated AnnData.
    batch_key, label_key : str
        Batch and cell-type columns.
    use_rep : str
        ``obsm`` key for the embedding.
    metric : str
        Distance metric (default ``'euclidean'``).
    verbose : bool
        Log summary statistics.

    Returns
    -------
    dict
        ``batch_asw``, ``celltype_asw``, ``batch_asw_per_label`` (DataFrame),
        ``celltype_asw_per_batch`` (DataFrame).
    """
    from sklearn.metrics import silhouette_samples, silhouette_score

    if verbose:
        logger.info("Computing ASW scores ...")

    for key, store, name in [
        (batch_key, "obs", "Batch key"),
        (label_key, "obs", "Label key"),
        (use_rep, "obsm", "Representation"),
    ]:
        if store == "obs" and key not in adata.obs.columns:
            raise ValueError(f"{name} '{key}' not found in adata.obs")
        if store == "obsm" and key not in adata.obsm:
            raise ValueError(f"{name} '{key}' not found in adata.obsm")

    X = adata.obsm[use_rep]
    batch_labels = adata.obs[batch_key].values
    celltype_labels = adata.obs[label_key].values

    # -- batch ASW (lower better) --------------------------------------------
    batch_asw = float(silhouette_score(X, batch_labels, metric=metric))
    batch_sil = silhouette_samples(X, batch_labels, metric=metric)

    batch_asw_per_label = []
    for label in np.unique(celltype_labels):
        mask = celltype_labels == label
        if mask.sum() > 1:
            batch_asw_per_label.append(
                {"cell_type": label, "batch_asw": float(batch_sil[mask].mean()), "n_cells": int(mask.sum())}
            )
    batch_asw_per_label_df = pd.DataFrame(batch_asw_per_label)

    # -- celltype ASW (higher better) ----------------------------------------
    celltype_asw = float(silhouette_score(X, celltype_labels, metric=metric))
    celltype_sil = silhouette_samples(X, celltype_labels, metric=metric)

    celltype_asw_per_batch = []
    for batch in np.unique(batch_labels):
        mask = batch_labels == batch
        if mask.sum() > 1:
            celltype_asw_per_batch.append(
                {"batch": batch, "celltype_asw": float(celltype_sil[mask].mean()), "n_cells": int(mask.sum())}
            )
    celltype_asw_per_batch_df = pd.DataFrame(celltype_asw_per_batch)

    if verbose:
        logger.info("  Batch ASW: %.3f (target ~0)", batch_asw)
        logger.info("  Cell-type ASW: %.3f (target >0.5)", celltype_asw)

    return {
        "batch_asw": batch_asw,
        "celltype_asw": celltype_asw,
        "batch_asw_per_label": batch_asw_per_label_df,
        "celltype_asw_per_batch": celltype_asw_per_batch_df,
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def plot_integration_metrics(
    adata: AnnData,
    batch_key: str,
    label_key: str,
    output_dir: str | Path,
    use_rep: str = "X_pca",
    method_name: str = "Integration",
) -> None:
    """Generate integration quality plots.

    Produces:

    1. UMAP coloured by batch and cell type
    2. iLISI / cLISI violin plots
    3. ASW summary bar chart
    4. Batch-mixing heatmap (proportions per cell type)

    All figures are saved via :func:`~skills.singlecell._lib.viz_utils.save_figure`.
    """
    import matplotlib.pyplot as plt
    import scanpy as sc  # lazy
    import seaborn as sns

    from .viz_utils import save_figure

    sns.set_style("ticks")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Generating integration quality plots for %s ...", method_name)

    # -- UMAP ----------------------------------------------------------------
    if "X_umap" not in adata.obsm:
        sc.pp.neighbors(adata, use_rep=use_rep)
        sc.tl.umap(adata)

    for colour_key, suffix in [(batch_key, "batch"), (label_key, "celltype")]:
        sc.pl.umap(adata, color=colour_key, title=f"{method_name}: {suffix}", show=False, save=False)
        fig = plt.gcf()
        save_figure(fig, output_dir, f"{method_name}_umap_{suffix}.png")

    # -- LISI + ASW -----------------------------------------------------------
    lisi = compute_lisi_scores(adata, batch_key, label_key, use_rep, verbose=False)
    asw = compute_asw_scores(adata, batch_key, label_key, use_rep, verbose=False)

    adata.obs["ilisi"] = lisi["ilisi"].values
    if "clisi" in lisi.columns:
        adata.obs["clisi"] = lisi["clisi"].values

    # iLISI violin
    plot_df = pd.DataFrame({"iLISI": adata.obs["ilisi"], "Cell Type": adata.obs[label_key]})
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.violinplot(data=plot_df, x="Cell Type", y="iLISI", ax=ax)
    ax.set_xlabel("")
    ax.set_ylabel("iLISI (higher = better mixing)")
    ax.set_title(f"{method_name}: Batch Mixing (iLISI)", fontweight="bold")
    plt.xticks(rotation=45, ha="right")
    sns.despine(ax=ax)
    fig.tight_layout()
    save_figure(fig, output_dir, f"{method_name}_ilisi_violin.png")

    # cLISI violin
    if "clisi" in adata.obs.columns:
        cplot_df = pd.DataFrame({"cLISI": adata.obs["clisi"], "Batch": adata.obs[batch_key]})
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.violinplot(data=cplot_df, x="Batch", y="cLISI", ax=ax)
        ax.set_xlabel("")
        ax.set_ylabel("cLISI (lower = better separation)")
        ax.set_title(f"{method_name}: Cell Type Separation (cLISI)", fontweight="bold")
        sns.despine(ax=ax)
        fig.tight_layout()
        save_figure(fig, output_dir, f"{method_name}_clisi_violin.png")

    # ASW summary bar
    asw_labels = ["Batch ASW\n(lower better)", "Cell Type ASW\n(higher better)"]
    asw_scores = [asw["batch_asw"], asw["celltype_asw"]]
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.bar(asw_labels, asw_scores, color=sns.color_palette("Set2", 2))
    ax.set_ylabel("ASW Score")
    ax.set_title(f"{method_name}: Average Silhouette Width", fontweight="bold")
    sns.despine(ax=ax)
    fig.tight_layout()
    save_figure(fig, output_dir, f"{method_name}_asw_summary.png")

    # Batch mixing heatmap
    batch_ct_counts = adata.obs.groupby([label_key, batch_key]).size().unstack(fill_value=0)
    batch_ct_proportions = batch_ct_counts.div(batch_ct_counts.sum(axis=1), axis=0)

    g = sns.clustermap(
        batch_ct_proportions,
        cmap="RdBu_r",
        center=0.5,
        cbar_kws={"label": "Proportion of cells"},
        annot=True,
        fmt=".2f",
        figsize=(10, 8),
        row_cluster=False,
        col_cluster=False,
    )
    g.ax_heatmap.set_title(f"{method_name}: Batch Distribution per Cell Type", fontweight="bold")
    g.ax_heatmap.set_xlabel("Batch")
    g.ax_heatmap.set_ylabel("Cell Type")
    save_figure(g.fig, output_dir, f"{method_name}_batch_mixing_heatmap.png")

    # -- metrics CSV ----------------------------------------------------------
    metrics = {
        "method": method_name,
        "representation": use_rep,
        "mean_ilisi": float(lisi["ilisi"].mean()),
        "median_ilisi": float(lisi["ilisi"].median()),
        "batch_asw": float(asw["batch_asw"]),
        "celltype_asw": float(asw["celltype_asw"]),
        "n_batches": int(adata.obs[batch_key].nunique()),
        "n_celltypes": int(adata.obs[label_key].nunique()),
    }
    if "clisi" in lisi.columns:
        metrics["mean_clisi"] = float(lisi["clisi"].mean())
        metrics["median_clisi"] = float(lisi["clisi"].median())

    metrics_file = output_dir / f"{method_name}_metrics_summary.csv"
    pd.DataFrame([metrics]).to_csv(metrics_file, index=False)
    logger.info("Metrics summary saved to: %s", metrics_file)


# ---------------------------------------------------------------------------
# Multi-method comparison
# ---------------------------------------------------------------------------


def compare_integration_methods(
    adata: AnnData,
    batch_key: str,
    label_key: str,
    methods: list[str],
    output_dir: str | Path,
) -> pd.DataFrame:
    """Compare multiple integration embeddings side-by-side.

    Computes iLISI, cLISI, and ASW for every representation listed in
    *methods* (e.g. ``['X_pca', 'X_scvi', 'X_harmony']``) and produces
    grouped bar charts.

    Parameters
    ----------
    adata : AnnData
        Must contain each representation in ``obsm``.
    batch_key, label_key : str
        Batch and cell-type columns.
    methods : list of str
        ``obsm`` keys to compare.
    output_dir : path-like
        Directory for plots and CSV.

    Returns
    -------
    DataFrame
        Comparison table with one row per method.
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    from .viz_utils import save_figure

    sns.set_style("ticks")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Comparing integration methods: %s", methods)

    rows: list[dict[str, Any]] = []
    for method in methods:
        if method not in adata.obsm:
            logger.warning("  %s not found in obsm -- skipping.", method)
            continue

        logger.info("  Computing metrics for %s ...", method)
        lisi = compute_lisi_scores(adata, batch_key, label_key, method, verbose=False)
        asw = compute_asw_scores(adata, batch_key, label_key, method, verbose=False)

        row: dict[str, Any] = {
            "Method": method.replace("X_", "").upper(),
            "Mean iLISI": float(lisi["ilisi"].mean()),
            "Batch ASW": float(asw["batch_asw"]),
            "Cell Type ASW": float(asw["celltype_asw"]),
        }
        if "clisi" in lisi.columns:
            row["Mean cLISI"] = float(lisi["clisi"].mean())
        else:
            row["Mean cLISI"] = float("nan")
        rows.append(row)

    results_df = pd.DataFrame(rows)
    results_df.to_csv(output_dir / "integration_comparison.csv", index=False)
    logger.info("Comparison table saved to: %s", output_dir / "integration_comparison.csv")

    # -- iLISI bar chart ------------------------------------------------------
    palette = sns.color_palette("Set2", n_colors=len(results_df))
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(results_df["Method"], results_df["Mean iLISI"], color=palette)
    ax.set_ylabel("Mean iLISI (higher = better)")
    ax.set_title("Integration Quality: Batch Mixing (iLISI)", fontweight="bold")
    sns.despine(ax=ax)
    fig.tight_layout()
    save_figure(fig, output_dir, "comparison_ilisi.png")

    # -- ASW grouped bar ------------------------------------------------------
    asw_melted = pd.melt(
        results_df[["Method", "Batch ASW", "Cell Type ASW"]],
        id_vars="Method",
        var_name="Metric",
        value_name="Score",
    )
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=asw_melted, x="Method", y="Score", hue="Metric", ax=ax)
    ax.set_ylabel("ASW Score")
    ax.set_title("Integration Quality: Average Silhouette Width", fontweight="bold")
    ax.legend(frameon=False)
    sns.despine(ax=ax)
    fig.tight_layout()
    save_figure(fig, output_dir, "comparison_asw.png")

    logger.info("Comparison complete.  Results in: %s", output_dir)
    return results_df
