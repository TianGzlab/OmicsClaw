"""Spatial cell type annotation algorithms.

Provides multiple methods for cell type annotation:
  - marker_based: Marker gene scoring (no reference needed, default)
  - tangram:      Deep learning mapping from scRNA-seq reference
  - scanvi:       Semi-supervised VAE transfer learning (scvi-tools)
  - cellassign:   Probabilistic marker-based assignment (scvi-tools)

Input matrix convention (per-method):
  - marker_based: adata.X (log-normalized) — scoring on continuous expression values
  - tangram:      adata.X (log-normalized) — both ref & spatial must be normalized
  - scanvi:       adata.layers["counts"] (raw) — NB/ZINB generative model
  - cellassign:   adata.layers["counts"] (raw) — NB likelihood model

Usage::

    from skills.spatial._lib.annotation import (
        annotate_marker_based,
        annotate_tangram,
        get_default_signatures,
        SUPPORTED_METHODS,
    )

    summary = annotate_marker_based(adata, cluster_key="leiden")
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse

from .adata_utils import get_spatial_key

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("marker_based", "tangram", "scanvi", "cellassign")

# Methods whose generative models assume raw counts (NB / ZINB likelihood).
COUNT_BASED_METHODS = ("scanvi", "cellassign")

# Methods that operate on continuous log-normalized expression values.
NORMALIZED_METHODS = ("marker_based", "tangram")

VALID_MARKER_RANK_METHODS = ("wilcoxon", "t-test", "t-test_overestim_var", "logreg")
VALID_MARKER_OVERLAP_METHODS = ("overlap_count", "overlap_coef", "jaccard")
VALID_MARKER_NORMALIZE_OPTIONS = ("reference", "data")

METHOD_PARAM_DEFAULTS = {
    "marker_based": {
        "cluster_key": "leiden",
        "species": "human",
        "rank_method": "wilcoxon",
        "n_marker_genes": 50,
        "overlap_method": "overlap_count",
        "overlap_normalize": "reference",
        "padj_cutoff": None,
        "min_score": 0.05,
    },
    "tangram": {
        "cell_type_key": "cell_type",
        "n_epochs": 500,
        "device": "auto",
        "n_train_genes": 2000,
    },
    "scanvi": {
        "cell_type_key": "cell_type",
        "n_hidden": 128,
        "n_latent": 10,
        "n_layers": 1,
        "max_epochs": 100,
        "layer": "counts",
    },
    "cellassign": {
        "layer": "counts",
        "max_epochs": 400,
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


# ---------------------------------------------------------------------------
# Marker signatures
# ---------------------------------------------------------------------------


def get_default_signatures(species: str) -> dict[str, list[str]]:
    """Return basic cell type marker gene signatures."""
    if species == "mouse":
        return {
            "T cells": ["Cd3d", "Cd3e", "Cd4", "Cd8a", "Trac"],
            "B cells": ["Cd79a", "Cd79b", "Ms4a1", "Cd19", "Pax5"],
            "Macrophages": ["Cd68", "Csf1r", "Adgre1", "Lyz2", "C1qa"],
            "NK cells": ["Nkg7", "Klrb1c", "Gzma", "Ncr1", "Prf1"],
            "Fibroblasts": ["Col1a1", "Col1a2", "Dcn", "Fn1", "Vim"],
            "Epithelial": ["Epcam", "Krt8", "Krt18", "Krt19", "Cdh1"],
            "Endothelial": ["Pecam1", "Cdh5", "Vwf", "Kdr", "Flt1"],
            "Smooth muscle": ["Acta2", "Myh11", "Tagln", "Des", "Cnn1"],
            "Neurons": ["Snap25", "Syt1", "Rbfox3", "Map2", "Tubb3"],
            "Astrocytes": ["Gfap", "Aqp4", "S100b", "Aldh1l1", "Slc1a3"],
            "Oligodendrocytes": ["Mbp", "Plp1", "Mog", "Mag", "Cnp"],
        }
    return {
        "T cells": ["CD3D", "CD3E", "CD4", "CD8A", "TRAC"],
        "B cells": ["CD79A", "CD79B", "MS4A1", "CD19", "PAX5"],
        "Macrophages": ["CD68", "CSF1R", "CD163", "LYZ", "C1QA"],
        "NK cells": ["NKG7", "KLRB1", "GZMA", "GNLY", "PRF1"],
        "Fibroblasts": ["COL1A1", "COL1A2", "DCN", "FN1", "VIM"],
        "Epithelial": ["EPCAM", "KRT8", "KRT18", "KRT19", "CDH1"],
        "Endothelial": ["PECAM1", "CDH5", "VWF", "KDR", "FLT1"],
        "Smooth muscle": ["ACTA2", "MYH11", "TAGLN", "DES", "CNN1"],
        "Neurons": ["SNAP25", "SYT1", "RBFOX3", "MAP2", "TUBB3"],
        "Astrocytes": ["GFAP", "AQP4", "S100B", "ALDH1L1", "SLC1A3"],
        "Oligodendrocytes": ["MBP", "PLP1", "MOG", "MAG", "CNP"],
    }


# ---------------------------------------------------------------------------
# Marker-based annotation
# ---------------------------------------------------------------------------


def annotate_marker_based(
    adata, *, cluster_key: str = "leiden", species: str = "human",
    rank_method: str = "wilcoxon",
    n_marker_genes: int = 50,
    overlap_method: str = "overlap_count",
    overlap_normalize: str | None = "reference",
    adj_pval_threshold: float | None = None,
    min_score: float = 0.05,
) -> dict:
    """Score-based cell type annotation using cluster marker genes.

    Uses ``adata.X`` (log-normalized) — ``rank_genes_groups`` and marker scoring
    operate on continuous expression values where gene magnitudes are comparable.
    Do not pass raw counts; the Wilcoxon test results and overlap scores depend
    on normalized, log-transformed expression.
    """
    if cluster_key not in adata.obs.columns:
        raise ValueError(f"Cluster key '{cluster_key}' not in adata.obs")
    if rank_method not in VALID_MARKER_RANK_METHODS:
        raise ValueError(
            f"Unsupported marker rank method '{rank_method}'. "
            f"Choose from {VALID_MARKER_RANK_METHODS}."
        )
    if overlap_method not in VALID_MARKER_OVERLAP_METHODS:
        raise ValueError(
            f"Unsupported marker overlap method '{overlap_method}'. "
            f"Choose from {VALID_MARKER_OVERLAP_METHODS}."
        )
    if overlap_normalize not in (*VALID_MARKER_NORMALIZE_OPTIONS, None):
        raise ValueError(
            f"Unsupported marker overlap normalization '{overlap_normalize}'. "
            f"Choose from {VALID_MARKER_NORMALIZE_OPTIONS} or None."
        )
    if n_marker_genes < 0:
        raise ValueError("n_marker_genes must be >= 0")

    adata.obs[cluster_key] = adata.obs[cluster_key].astype("category")
    n_rank_genes = n_marker_genes or adata.n_vars
    logger.info(
        "Finding marker genes per cluster (%s) with rank method '%s' ...",
        cluster_key,
        rank_method,
    )
    sc.tl.rank_genes_groups(
        adata,
        cluster_key,
        method=rank_method,
        n_genes=n_rank_genes,
        use_raw=False,
    )

    marker_signatures = {label: sorted(set(genes)) for label, genes in get_default_signatures(species).items()}
    overlap_kwargs = {
        "key": "rank_genes_groups",
        "method": overlap_method,
        "top_n_markers": n_marker_genes or None,
        "adj_pval_threshold": adj_pval_threshold,
        "inplace": False,
    }
    if overlap_method == "overlap_count":
        overlap_kwargs["normalize"] = overlap_normalize
    elif overlap_normalize is not None:
        logger.warning(
            "Ignoring overlap normalization '%s' because it only applies to overlap_count.",
            overlap_normalize,
        )

    overlap_df = sc.tl.marker_gene_overlap(adata, marker_signatures, **overlap_kwargs)
    adata.uns["marker_gene_overlap"] = overlap_df

    cluster_annotations = {}
    cluster_scores = {}
    clusters = sorted(adata.obs[cluster_key].cat.categories, key=str)

    for cluster in clusters:
        cluster_name = str(cluster)
        if cluster_name not in overlap_df.columns:
            cluster_annotations[cluster_name] = "Unknown"
            cluster_scores[cluster_name] = 0.0
            continue
        best_type = str(overlap_df[cluster_name].idxmax())
        best_score = float(overlap_df[cluster_name].max())
        if best_score < min_score:
            best_type = "Unknown"
        cluster_annotations[cluster_name] = best_type
        cluster_scores[cluster_name] = round(best_score, 3)

    adata.obs["cell_type"] = adata.obs[cluster_key].astype(str).map(cluster_annotations)
    adata.obs["cell_type"] = pd.Categorical(adata.obs["cell_type"])

    counts = adata.obs["cell_type"].value_counts().to_dict()
    n_types = adata.obs["cell_type"].nunique()
    logger.info("Annotated %d clusters -> %d cell types", len(clusters), n_types)

    return {
        "method": "marker_based", "n_clusters": len(clusters),
        "n_cell_types": n_types, "cluster_annotations": cluster_annotations,
        "cluster_scores": cluster_scores, "cell_type_counts": counts,
        "species": species, "cluster_key": cluster_key,
        "rank_method": rank_method, "n_marker_genes": n_marker_genes or adata.n_vars,
        "overlap_method": overlap_method, "overlap_normalize": overlap_normalize,
        "marker_padj_cutoff": adj_pval_threshold,
    }


# ---------------------------------------------------------------------------
# Tangram
# ---------------------------------------------------------------------------


def annotate_tangram(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_epochs: int = 500, device: str = "auto", n_train_genes: int = 2000,
) -> dict:
    """Transfer cell type labels from scRNA-seq reference using Tangram.

    Uses ``adata.X`` (log-normalized) for both scRNA-seq reference and spatial
    data.  Tangram optimizes a mapping from sc → spatial by comparing expression
    values directly; both sides must be on the same normalized scale.  Feeding
    raw counts causes scale mismatch and mapping failure.

    Robust to device availability (CUDA/CPU), and rigorously intersects
    overlapping training genes to avoid crashes.
    """
    from .dependency_manager import require
    require("tangram", feature="Tangram cell type annotation")
    import tangram as tg
    import torch

    logger.info("Loading reference data: %s", reference_path)
    adata_ref = sc.read_h5ad(reference_path)

    if cell_type_key not in adata_ref.obs.columns:
        raise ValueError(f"Cell type key '{cell_type_key}' not in reference")

    if n_train_genes < 0:
        raise ValueError("n_train_genes must be >= 0")

    if n_train_genes == 0:
        training_genes = list(adata_ref.var_names)
    elif "highly_variable" in adata_ref.var.columns:
        training_genes = list(adata_ref.var_names[adata_ref.var["highly_variable"]])[:n_train_genes]
    else:
        logger.info("Computing highly variable genes for reference...")
        try:
            sc.pp.highly_variable_genes(adata_ref, n_top_genes=n_train_genes, flavor="seurat_v3")
        except Exception:
            sc.pp.highly_variable_genes(adata_ref, n_top_genes=n_train_genes)
        training_genes = list(adata_ref.var_names[adata_ref.var["highly_variable"]])[:n_train_genes]

    # Tangram needs log-normalized expression for both ref and spatial.
    # Use adata.X directly (should be normalize_total + log1p).
    adata_sp = adata.copy()
    logger.info("Tangram: using adata.X (log-normalized) for spatial mapping")

    spatial_key = get_spatial_key(adata)
    if spatial_key and spatial_key not in adata_sp.obsm:
        adata_sp.obsm[spatial_key] = adata.obsm[spatial_key].copy()

    common_genes = list(set(training_genes) & set(adata_sp.var_names))
    if len(common_genes) < 50:
        raise ValueError(f"Too few overlapping HVGs ({len(common_genes)}) between reference and spatial data")

    tg.pp_adatas(adata_ref, adata_sp, genes=common_genes)
    
    resolved_device = device
    if device == "auto":
        if torch.cuda.is_available():
            resolved_device = "cuda:0"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            resolved_device = "mps"
        else:
            resolved_device = "cpu"

    logger.info("Running Tangram mapping (%d epochs) on device '%s' ...", n_epochs, resolved_device)
    ad_map = tg.map_cells_to_space(
        adata_ref,
        adata_sp,
        mode="cells",
        num_epochs=n_epochs,
        device=resolved_device,
    )
    
    logger.info("Projecting cell type annotations ...")
    tg.project_cell_annotations(ad_map, adata_sp, annotation=cell_type_key)

    if "tangram_ct_pred" in adata_sp.obsm:
        ct_pred = adata_sp.obsm["tangram_ct_pred"]
        # Safe division to avoid NaN probabilities
        row_sums = ct_pred.sum(axis=1)
        row_sums[row_sums == 0] = 1.0
        ct_prob = ct_pred.div(row_sums, axis=0)
        
        adata.obs["cell_type"] = pd.Categorical(ct_prob.idxmax(axis=1))
        adata.obsm["tangram_ct_pred"] = ct_pred
        adata.uns["tangram_cell_type_names"] = list(ct_prob.columns)
    else:
        raise RuntimeError("Tangram did not produce cell type predictions")

    counts = adata.obs["cell_type"].value_counts().to_dict()
    return {
        "method": "tangram", "n_cell_types": adata.obs["cell_type"].nunique(),
        "cell_type_counts": counts, "n_training_genes": len(common_genes),
        "n_epochs": n_epochs, "device": resolved_device,
        "cell_type_key": cell_type_key,
    }


# ---------------------------------------------------------------------------
# scANVI
# ---------------------------------------------------------------------------


def annotate_scanvi(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    batch_key: str | None = None, layer: str | None = "counts",
    n_hidden: int = 128, n_latent: int = 10, n_layers: int = 1,
    max_epochs: int = 100,
) -> dict:
    """Transfer cell type labels using scANVI semi-supervised VAE.

    Uses raw counts from ``adata.layers["counts"]`` — scANVI's generative model
    assumes a negative-binomial / ZINB likelihood over integer counts.  Passing
    log-normalized values as "counts" will produce silently wrong results.
    Falls back to ``adata.X`` with a warning if no counts layer is available.
    """
    from .dependency_manager import require
    require("scvi", feature="scANVI cell type annotation")
    import scvi

    logger.info("Loading reference: %s", reference_path)
    adata_ref = sc.read_h5ad(reference_path)

    if cell_type_key not in adata_ref.obs.columns:
        raise ValueError(f"'{cell_type_key}' not found in reference adata.obs")

    common_genes = list(set(adata_ref.var_names) & set(adata.var_names))
    if len(common_genes) < 100:
        raise ValueError(f"Insufficient gene overlap: {len(common_genes)} common genes")

    # Filter to highly variable genes to vastly improve VAE speed and accuracy
    if "highly_variable" in adata_ref.var.columns:
        ref_hvgs = set(adata_ref.var_names[adata_ref.var["highly_variable"]])
        common_hvgs = list(set(common_genes) & ref_hvgs)
        if len(common_hvgs) > 500:
            logger.info("Restricting scANVI to %d overlapping highly variable genes", len(common_hvgs))
            common_genes = common_hvgs
        else:
            logger.info("Only %d overlapping HVGs found; using all %d common genes", len(common_hvgs), len(common_genes))
    else:
        logger.info("No 'highly_variable' flag in reference; using all %d common genes", len(common_genes))

    adata_ref_sub = adata_ref[:, common_genes].copy()
    adata_sub = adata[:, common_genes].copy()

    requested_layer = layer
    if requested_layer:
        for label, ad in [("reference", adata_ref_sub), ("spatial", adata_sub)]:
            if requested_layer not in ad.layers:
                if requested_layer == "counts":
                    counts_layer = _get_counts_layer(ad)
                    if counts_layer is None:
                        logger.warning(
                            "scANVI %s: no '%s' layer or adata.raw found; copying adata.X. "
                            "If adata.X is log-normalized, results will be incorrect. "
                            "Ensure preprocessing saves raw counts: adata.layers['counts'] = adata.X.copy()",
                            label,
                            requested_layer,
                        )
                        ad.layers["counts"] = ad.X.copy()
                else:
                    raise ValueError(f"Requested layer '{requested_layer}' not found in {label} AnnData")
    else:
        for label, ad in [("reference", adata_ref_sub), ("spatial", adata_sub)]:
            counts_layer = _get_counts_layer(ad)
            if counts_layer is not None:
                logger.info("scANVI %s: using layers['%s'] (raw counts)", label, counts_layer)
                requested_layer = counts_layer
            else:
                logger.warning(
                    "scANVI %s: no 'counts' layer or adata.raw found; copying adata.X. "
                    "If adata.X is log-normalized, results will be incorrect. "
                    "Ensure preprocessing saves raw counts: adata.layers['counts'] = adata.X.copy()",
                    label,
                )
                ad.layers["counts"] = ad.X.copy()
                requested_layer = "counts"

    if batch_key is not None:
        if batch_key not in adata_ref_sub.obs.columns:
            raise ValueError(f"batch_key '{batch_key}' not found in reference adata.obs")
        if batch_key not in adata_sub.obs.columns:
            raise ValueError(f"batch_key '{batch_key}' not found in spatial adata.obs")

    train_kwargs = {
        "early_stopping": True,
        "early_stopping_patience": 15,
        "check_val_every_n_epoch": 1,
        "max_epochs": max_epochs,
    }

    scvi.model.SCVI.setup_anndata(
        adata_ref_sub,
        labels_key=cell_type_key,
        batch_key=batch_key,
        layer=requested_layer,
    )
    scvi_model = scvi.model.SCVI(
        adata_ref_sub,
        n_hidden=n_hidden,
        n_latent=n_latent,
        n_layers=n_layers,
    )
    logger.info("Training SCVI on reference...")
    scvi_model.train(**train_kwargs)

    scanvi_model = scvi.model.SCANVI.from_scvi_model(
        scvi_model,
        "Unknown",
        labels_key=cell_type_key,
    )
    logger.info("Training SCANVI from SCVI...")
    scanvi_model.train(max_epochs=max_epochs, early_stopping=True, early_stopping_patience=10)

    adata_sub.obs[cell_type_key] = "Unknown"
    scvi.model.SCANVI.setup_anndata(
        adata_sub,
        labels_key=cell_type_key,
        unlabeled_category="Unknown",
        batch_key=batch_key,
        layer=requested_layer,
    )
    
    logger.info("Loading query data and adapting SCANVI model...")
    query_model = scvi.model.SCANVI.load_query_data(adata_sub, scanvi_model)
    query_model.train(max_epochs=max_epochs, early_stopping=True, early_stopping_patience=10)

    predictions = query_model.predict()
    adata.obs["cell_type"] = pd.Categorical(predictions)
    
    # Store probability matrix in obsm for downstream confidence evaluation
    probabilities = query_model.predict(soft=True)
    adata.obsm["scanvi_probabilities"] = probabilities.values if hasattr(probabilities, "values") else probabilities
    if hasattr(probabilities, "columns"):
        adata.uns["scanvi_cell_type_names"] = list(probabilities.columns)
    
    # Calculate confidence per cell
    confidence = adata.obsm["scanvi_probabilities"].max(axis=1)
    adata.obs["scanvi_confidence"] = confidence

    counts = adata.obs["cell_type"].value_counts().to_dict()
    mean_conf = float(np.mean(confidence))
    logger.info("scANVI: %d cell types predicted (Mean confidence: %.3f)", len(counts), mean_conf)

    return {
        "method": "scanvi", "n_cell_types": len(counts), "cell_type_counts": counts,
        "n_common_genes": len(common_genes), "n_hidden": n_hidden,
        "n_latent": n_latent, "n_layers": n_layers,
        "max_epochs": max_epochs, "layer": requested_layer,
        "batch_key": batch_key, "cell_type_key": cell_type_key,
        "mean_confidence": round(mean_conf, 4),
    }


# ---------------------------------------------------------------------------
# CellAssign
# ---------------------------------------------------------------------------


def annotate_cellassign(
    adata, *, marker_genes: dict[str, list[str]], max_epochs: int = 400,
    batch_key: str | None = None, layer: str | None = None,
) -> dict:
    """Assign cell types using CellAssign probabilistic model.

    Uses raw counts from ``adata.layers["counts"]`` (or the explicit ``layer``
    argument) — CellAssign assumes a negative-binomial count likelihood.
    Feeding log-normalized data will produce completely wrong assignments.
    Size factors are computed from the same raw-count matrix.
    """
    from .dependency_manager import require
    require("scvi", feature="CellAssign cell type annotation")
    from scvi.external import CellAssign

    # validate markers
    valid_markers = {}
    all_genes = set(adata.var_names)
    dropped_genes: dict[str, list[str]] = {}
    for ct, genes in marker_genes.items():
        found = [g for g in genes if g in all_genes]
        missing = [g for g in genes if g not in all_genes]
        if found:
            valid_markers[ct] = found
        if missing:
            dropped_genes[ct] = missing

    if dropped_genes:
        n_dropped = sum(len(v) for v in dropped_genes.values())
        logger.warning("Dropped %d marker gene(s) not present in dataset", n_dropped)

    if not valid_markers:
        raise ValueError("No marker genes found in the dataset")

    cell_types = list(valid_markers.keys())
    marker_gene_list = sorted({g for genes in valid_markers.values() for g in genes})

    logger.info("CellAssign: %d cell types, %d marker genes", len(cell_types), len(marker_gene_list))

    # binary marker matrix
    marker_matrix = pd.DataFrame(
        np.zeros((len(marker_gene_list), len(cell_types)), dtype=np.float64),
        index=marker_gene_list, columns=cell_types,
    )
    for ct, genes in valid_markers.items():
        for g in genes:
            marker_matrix.loc[g, ct] = 1.0

    # Determine the counts layer for CellAssign (NB model needs raw counts).
    if layer is not None and layer in adata.layers:
        counts_layer_name = layer
        logger.info("CellAssign: using explicit layer='%s'", layer)
    else:
        counts_layer_name = _get_counts_layer(adata)
        if counts_layer_name is not None:
            logger.info("CellAssign: using layers['%s'] (raw counts)", counts_layer_name)
        else:
            logger.warning(
                "CellAssign: no 'counts' layer or adata.raw found; using adata.X. "
                "If adata.X is log-normalized, results will be completely wrong. "
                "Ensure preprocessing saves raw counts: adata.layers['counts'] = adata.X.copy()"
            )

    # Compute size factors from the counts matrix (not log-normalized).
    data_for_libsize = adata.layers[counts_layer_name] if counts_layer_name else adata.X
    lib_size = np.asarray(data_for_libsize.sum(axis=1)).flatten().astype(np.float64)
    
    mean_lib = np.mean(lib_size)
    if mean_lib == 0:
        raise ValueError("All cells have zero total counts")
    size_factors = np.maximum(lib_size / mean_lib, 1e-6)

    adata_sub = adata[:, marker_gene_list].copy()
    adata_sub.obs["size_factors"] = size_factors

    setup_kwargs: dict = {"size_factor_key": "size_factors"}
    if batch_key is not None:
        if batch_key not in adata_sub.obs.columns:
            raise ValueError(f"batch_key '{batch_key}' not found in adata.obs")
        setup_kwargs["batch_key"] = batch_key
    if counts_layer_name is not None and counts_layer_name in adata_sub.layers:
        setup_kwargs["layer"] = counts_layer_name

    CellAssign.setup_anndata(adata_sub, **setup_kwargs)
    model = CellAssign(adata_sub, marker_matrix)
    
    train_kwargs = {
        "early_stopping": True, 
        "early_stopping_patience": 15, 
        "check_val_every_n_epoch": 1,
        "max_epochs": max_epochs
    }
    logger.info("Training CellAssign (max_epochs=%d) ...", max_epochs)
    model.train(**train_kwargs)

    predictions = model.predict()
    labels = predictions.idxmax(axis=1).values
    confidence = predictions.max(axis=1).values

    adata.obs["cell_type"] = pd.Categorical(labels)
    adata.obs["cellassign_confidence"] = confidence
    
    # Store probability matrix in obsm safely
    adata.obsm["cellassign_probabilities"] = predictions.values if hasattr(predictions, "values") else predictions
    if hasattr(predictions, "columns"):
        adata.uns["cellassign_cell_type_names"] = list(predictions.columns)

    counts = adata.obs["cell_type"].value_counts().to_dict()
    mean_conf = float(np.mean(confidence))
    logger.info("CellAssign: %d cell types, mean confidence %.3f", len(counts), mean_conf)

    # Avoid Pyre lint issue with round() on float by using string formatting
    mean_conf_rounded = float(f"{mean_conf:.4f}")

    return {
        "method": "cellassign", "n_cell_types": len(counts), "cell_type_counts": counts,
        "n_marker_genes": len(marker_gene_list), "mean_confidence": mean_conf_rounded,
        "cell_type_names": cell_types, "max_epochs": max_epochs,
        "batch_key": batch_key, "layer": counts_layer_name,
    }
