"""Spatial cell type annotation algorithms.

Provides multiple methods for cell type annotation:
  - marker_based: Marker gene scoring (no reference needed, default)
  - tangram:      Deep learning mapping from scRNA-seq reference
  - scanvi:       Semi-supervised VAE transfer learning (scvi-tools)
  - cellassign:   Probabilistic marker-based assignment (scvi-tools)

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

from .adata_utils import get_spatial_key

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("marker_based", "tangram", "scanvi", "cellassign")


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
    n_top_markers: int = 5,
) -> dict:
    """Score-based cell type annotation using cluster marker genes."""
    if cluster_key not in adata.obs.columns:
        raise ValueError(f"Cluster key '{cluster_key}' not in adata.obs")

    adata.obs[cluster_key] = adata.obs[cluster_key].astype("category")
    logger.info("Finding marker genes per cluster (%s) ...", cluster_key)
    sc.tl.rank_genes_groups(adata, cluster_key, method="wilcoxon", n_genes=50)

    marker_signatures = get_default_signatures(species)
    cluster_annotations = {}
    cluster_scores = {}
    clusters = sorted(adata.obs[cluster_key].cat.categories, key=str)

    for cluster in clusters:
        markers_df = sc.get.rank_genes_groups_df(adata, group=str(cluster))
        top_markers = markers_df.head(50)["names"].tolist()

        best_type, best_score = "Unknown", 0.0
        for cell_type, sig_genes in marker_signatures.items():
            overlap = set(top_markers[:30]) & set(sig_genes)
            score = len(overlap) / max(len(sig_genes), 1)
            if score > best_score:
                best_score = score
                best_type = cell_type

        if best_score < 0.05:
            best_type = "Unknown"
        cluster_annotations[str(cluster)] = best_type
        cluster_scores[str(cluster)] = round(best_score, 3)

    adata.obs["cell_type"] = adata.obs[cluster_key].astype(str).map(cluster_annotations)
    adata.obs["cell_type"] = pd.Categorical(adata.obs["cell_type"])

    counts = adata.obs["cell_type"].value_counts().to_dict()
    n_types = adata.obs["cell_type"].nunique()
    logger.info("Annotated %d clusters -> %d cell types", len(clusters), n_types)

    return {
        "method": "marker_based", "n_clusters": len(clusters),
        "n_cell_types": n_types, "cluster_annotations": cluster_annotations,
        "cluster_scores": cluster_scores, "cell_type_counts": counts, "species": species,
    }


# ---------------------------------------------------------------------------
# Tangram
# ---------------------------------------------------------------------------


def annotate_tangram(
    adata, *, reference_path: str, cell_type_key: str = "cell_type", n_epochs: int = 500,
) -> dict:
    """Transfer cell type labels from scRNA-seq reference using Tangram."""
    from .dependency_manager import require
    require("tangram", feature="Tangram cell type annotation")
    import tangram as tg

    logger.info("Loading reference data: %s", reference_path)
    adata_ref = sc.read_h5ad(reference_path)

    if cell_type_key not in adata_ref.obs.columns:
        raise ValueError(f"Cell type key '{cell_type_key}' not in reference")

    if "highly_variable" in adata_ref.var.columns:
        training_genes = list(adata_ref.var_names[adata_ref.var["highly_variable"]])
    else:
        sc.pp.highly_variable_genes(adata_ref, n_top_genes=2000)
        training_genes = list(adata_ref.var_names[adata_ref.var["highly_variable"]])

    adata_sp = adata.raw.to_adata() if adata.raw is not None else adata.copy()
    spatial_key = get_spatial_key(adata)
    if spatial_key and spatial_key not in adata_sp.obsm:
        adata_sp.obsm[spatial_key] = adata.obsm[spatial_key].copy()

    tg.pp_adatas(adata_ref, adata_sp, genes=training_genes)
    logger.info("Running Tangram mapping (%d epochs) ...", n_epochs)
    ad_map = tg.map_cells_to_space(adata_ref, adata_sp, mode="cells", num_epochs=n_epochs, device="cpu")
    tg.project_cell_annotations(ad_map, adata_sp, annotation=cell_type_key)

    if "tangram_ct_pred" in adata_sp.obsm:
        ct_pred = adata_sp.obsm["tangram_ct_pred"]
        ct_prob = ct_pred.div(ct_pred.sum(axis=1), axis=0)
        adata.obs["cell_type"] = pd.Categorical(ct_prob.idxmax(axis=1))
        adata.obsm["tangram_ct_pred"] = ct_pred
    else:
        raise RuntimeError("Tangram did not produce cell type predictions")

    counts = adata.obs["cell_type"].value_counts().to_dict()
    return {
        "method": "tangram", "n_cell_types": adata.obs["cell_type"].nunique(),
        "cell_type_counts": counts, "n_training_genes": len(training_genes), "n_epochs": n_epochs,
    }


# ---------------------------------------------------------------------------
# scANVI
# ---------------------------------------------------------------------------


def annotate_scanvi(
    adata, *, reference_path: str, cell_type_key: str = "cell_type",
    n_latent: int = 10, n_epochs: int = 100,
) -> dict:
    """Transfer cell type labels using scANVI semi-supervised VAE."""
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

    logger.info("Gene overlap: %d common genes", len(common_genes))
    adata_ref_sub = adata_ref[:, common_genes].copy()
    adata_sub = adata[:, common_genes].copy()

    if "counts" not in adata_ref_sub.layers:
        adata_ref_sub.layers["counts"] = adata_ref_sub.X.copy()
    if "counts" not in adata_sub.layers:
        adata_sub.layers["counts"] = adata_sub.X.copy()

    scvi.model.SCVI.setup_anndata(adata_ref_sub, labels_key=cell_type_key, layer="counts")
    scvi_model = scvi.model.SCVI(adata_ref_sub, n_latent=n_latent)
    scvi_model.train(max_epochs=200, early_stopping=True)

    scanvi_model = scvi.model.SCANVI.from_scvi_model(scvi_model, "Unknown")
    scanvi_model.train(max_epochs=n_epochs, early_stopping=True)

    adata_sub.obs[cell_type_key] = "Unknown"
    scvi.model.SCANVI.setup_anndata(adata_sub, labels_key=cell_type_key, unlabeled_category="Unknown", layer="counts")
    query_model = scvi.model.SCANVI.load_query_data(adata_sub, scanvi_model)
    query_model.train(max_epochs=100, early_stopping=True)

    predictions = query_model.predict()
    adata.obs["cell_type"] = pd.Categorical(predictions)

    counts = adata.obs["cell_type"].value_counts().to_dict()
    logger.info("scANVI: %d cell types predicted", len(counts))

    return {
        "method": "scanvi", "n_cell_types": len(counts), "cell_type_counts": counts,
        "n_common_genes": len(common_genes), "n_latent": n_latent,
    }


# ---------------------------------------------------------------------------
# CellAssign
# ---------------------------------------------------------------------------


def annotate_cellassign(
    adata, *, marker_genes: dict[str, list[str]], max_epochs: int = 400,
    batch_key: str | None = None, layer: str | None = None,
) -> dict:
    """Assign cell types using CellAssign probabilistic model."""
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

    # size factors
    data_for_libsize = adata.layers[layer] if layer else adata.X
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
    if layer is not None and layer in adata_sub.layers:
        setup_kwargs["layer"] = layer

    CellAssign.setup_anndata(adata_sub, **setup_kwargs)
    model = CellAssign(adata_sub, marker_matrix)
    logger.info("Training CellAssign (max_epochs=%d) ...", max_epochs)
    model.train(max_epochs=max_epochs, early_stopping=True)

    predictions = model.predict()
    labels = predictions.idxmax(axis=1).values
    confidence = predictions.max(axis=1).values

    adata.obs["cell_type"] = pd.Categorical(labels)
    adata.obs["cellassign_confidence"] = confidence
    adata.obsm["cellassign_probabilities"] = predictions.values

    counts = adata.obs["cell_type"].value_counts().to_dict()
    mean_confidence = float(np.mean(confidence))
    logger.info("CellAssign: %d cell types, mean confidence %.3f", len(counts), mean_confidence)

    return {
        "method": "cellassign", "n_cell_types": len(counts), "cell_type_counts": counts,
        "n_marker_genes": len(marker_gene_list), "mean_confidence": round(mean_confidence, 4),
        "cell_type_names": cell_types,
    }
