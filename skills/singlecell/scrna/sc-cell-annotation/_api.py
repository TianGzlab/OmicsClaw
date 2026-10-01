"""sc-cell-annotation's function library: label cells with cell types.

In a step: ``annotation = load_skill("sc-cell-annotation")``. Every annotate
function writes ``obs['cell_type']`` (and ``obs['annotation_score']`` when the
method gives one) in place and returns the same AnnData; :func:`run_info`
returns what the run did, including any fallback. The functions read and write
no files except a marker file or reference you name. ``singler`` and ``scmap``
run R through ``Rscript``.
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
from skills.singlecell._lib import annotation as sc_annotation_utils
from skills.singlecell._lib.adata_utils import get_matrix_contract

__all__ = [
    "annotate",
    "annotate_markers",
    "annotate_manual",
    "annotate_celltypist",
    "annotate_popv",
    "annotate_knnpredict",
    "annotate_singler",
    "annotate_scmap",
    "annotate_scsa",
    "run_info",
    "annotation_table",
    "cluster_annotation_matrix",
    "annotation_figure",
]

logger = logging.getLogger(__name__)

METHODS = ("markers", "manual", "celltypist", "popv", "knnpredict", "singler", "scmap", "scsa")
_RUN_KEY = "omicsclaw_sc_cell_annotation_run"


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def _remember(adata, cluster_key, summary: dict):
    adata.uns[_RUN_KEY] = json.dumps({"cluster_key": cluster_key, "summary": summary}, default=_json_default)
    return adata


def annotate(
    adata,
    *,
    method: str = "markers",
    cluster_key: str | None = None,
    markers: dict[str, list[str]] | None = None,
    marker_file: str | None = None,
    model: str = "Immune_All_Low",
    majority_voting: bool = False,
    reference: str = "HPCA",
    manual_map: str | None = None,
    manual_map_file: str | None = None,
    species: str = "Human",
    tissue: str = "All",
    scsa_foldchange: float = 1.5,
    scsa_pvalue: float = 0.05,
):
    """Annotate cell types with the chosen method; the single entry point to the method functions.

    :param method: One of ``markers`` (default), ``manual``, ``celltypist``, ``popv``,
        ``knnpredict``, ``singler``, ``scmap``, ``scsa``. See the method functions for
        what each needs.
    :param cluster_key: The ``obs`` column with cluster labels. Default ``None``: the
        matrix contract's primary cluster key, else the first of ``leiden``,
        ``louvain``, ``seurat_clusters``, ``cluster``, ``cell_type`` present.
    :param markers: ``markers`` only: cell type to marker genes. Default: the built-in human set.
    :param marker_file: ``markers`` only: a JSON or CSV marker file, used instead of *markers*.
    :param model: ``celltypist`` only. Default ``"Immune_All_Low"``.
    :param majority_voting: ``celltypist`` only. Default ``False``.
    :param reference: ``popv``, ``knnpredict``: a labelled ``.h5ad`` path; ``singler``,
        ``scmap``: a celldex atlas name. Default ``"HPCA"``.
    :param manual_map: ``manual`` only: inline mapping such as ``"0=T cell;1,2=Myeloid"``.
    :param manual_map_file: ``manual`` only: a mapping file (json/csv/tsv/txt).
    :param species: ``scsa`` only: ``"Human"`` or ``"Mouse"``. Default ``"Human"``.
    :param tissue: ``scsa`` only: CellMarker tissue filter. Default ``"All"``.
    :param scsa_foldchange: ``scsa`` only. Default 1.5.
    :param scsa_pvalue: ``scsa`` only. Default 0.05.
    :returns: The same AnnData.
    :raises ValueError: an unknown method, or what the chosen method raises.
    """
    if method not in METHODS:
        raise ValueError(f"unknown annotation method {method!r}; choose one of {', '.join(METHODS)}")
    if method == "markers":
        return annotate_markers(adata, cluster_key=cluster_key, markers=markers, marker_file=marker_file)
    if method == "manual":
        return annotate_manual(adata, cluster_key=cluster_key, manual_map=manual_map, manual_map_file=manual_map_file)
    if method == "celltypist":
        return annotate_celltypist(adata, model=model, majority_voting=majority_voting, cluster_key=cluster_key)
    if method == "popv":
        return annotate_popv(adata, reference=reference, cluster_key=cluster_key)
    if method == "knnpredict":
        return annotate_knnpredict(adata, reference=reference, cluster_key=cluster_key)
    if method == "singler":
        return annotate_singler(adata, reference=reference, cluster_key=cluster_key)
    if method == "scmap":
        return annotate_scmap(adata, reference=reference, cluster_key=cluster_key)
    return annotate_scsa(adata, cluster_key=cluster_key, species=species, tissue=tissue,
                         foldchange=scsa_foldchange, pvalue=scsa_pvalue)


def annotate_markers(adata, *, cluster_key: str | None = None, markers: dict[str, list[str]] | None = None,
                     marker_file: str | None = None):
    """Label each cluster with the cell type whose marker genes have the highest mean expression in it.

    Every cell of a cluster gets the cluster's label; a cluster where no marker
    gene is expressed is ``Unknown``. Gene names are matched exactly, or
    case-insensitively when nothing matches exactly (human markers on mouse data).

    :param cluster_key: As in :func:`annotate`.
    :param markers: Cell type to marker genes. Default: the built-in human set
        (PBMC, brain and general stromal types). Give tissue-specific markers for other tissues.
    :param marker_file: A JSON (``{"T cell": ["CD3D", ...]}``) or CSV (``T cell,CD3D;CD3E``)
        marker file, used instead of *markers*.
    :returns: The same AnnData with ``obs['cell_type']`` and ``obs['annotation_score']``
        (the winning mean expression).
    :raises ValueError: the cluster column is missing.
    """
    key = _resolve_cluster_key(adata, cluster_key) or "leiden"
    return _remember(adata, key, _annotate_markers(adata, markers=markers, cluster_key=key, marker_file=marker_file))


def annotate_manual(adata, *, cluster_key: str | None = None, manual_map: str | None = None,
                    manual_map_file: str | None = None):
    """Relabel clusters from a mapping the user gives.

    :param cluster_key: As in :func:`annotate`.
    :param manual_map: Inline mapping such as ``"0=T cell;1,2=Myeloid"``.
    :param manual_map_file: A mapping file (json, csv, tsv or txt), used instead of *manual_map*.
    :returns: The same AnnData with ``obs['cell_type']``.
    :raises ValueError: neither mapping is given.
    """
    key = _resolve_cluster_key(adata, cluster_key)
    return _remember(adata, key, _annotate_manual(adata, cluster_key=key, manual_map=manual_map,
                                                  manual_map_file=manual_map_file))


def annotate_celltypist(adata, *, model: str = "Immune_All_Low", majority_voting: bool = False,
                        cluster_key: str | None = None):
    """Per-cell labels from a pretrained CellTypist model.

    CellTypist needs log1p-normalised expression to 10,000 counts; when the input
    fails that check, or the model cannot be loaded, the function falls back to
    :func:`annotate_markers` and records the reason (``run_info(adata)["summary"]["fallback_reason"]``).

    :param model: A CellTypist model name or ``.pkl``. Default ``"Immune_All_Low"`` (immune
        cells, fine labels); choose a tissue model for other data. Models download on first use.
    :param majority_voting: Smooth labels over over-clustered communities. Default ``False``.
    :param cluster_key: Recorded for later steps; CellTypist labels cells individually.
    :returns: The same AnnData with ``obs['cell_type']``, ``obs['annotation_score']`` and
        ``obsm['cell_type_prob']``.
    """
    key = _resolve_cluster_key(adata, cluster_key)
    return _remember(adata, key, _annotate_celltypist(adata, model, majority_voting=majority_voting))


def annotate_popv(adata, *, reference: str = "HPCA", cluster_key: str | None = None):
    """Labels transferred from a labelled reference AnnData by PopV-style consensus.

    :param reference: Path to a labelled ``.h5ad`` (a ``cell_type`` column in ``obs``).
    :param cluster_key: As in :func:`annotate`; used for the cluster consensus.
    :returns: The same AnnData with ``obs['cell_type']``.
    """
    key = _resolve_cluster_key(adata, cluster_key)
    return _remember(adata, key, _annotate_popv(adata, reference, cluster_key=key))


def annotate_knnpredict(adata, *, reference: str = "HPCA", cluster_key: str | None = None):
    """Labels transferred from a labelled reference AnnData by nearest neighbours (SCOP KNNPredict style).

    :param reference: Path to a labelled ``.h5ad`` (a ``cell_type`` column in ``obs``).
    :param cluster_key: As in :func:`annotate`.
    :returns: The same AnnData with ``obs['cell_type']`` and ``obs['annotation_score']``.
    """
    key = _resolve_cluster_key(adata, cluster_key)
    return _remember(adata, key, _annotate_knnpredict(adata, reference, cluster_key=key))


def annotate_singler(adata, *, reference: str = "HPCA", cluster_key: str | None = None):
    """Per-cell labels from SingleR against a celldex atlas, run in R.

    :param reference: A celldex atlas: ``HPCA`` (default), ``BlueprintEncode``, ``Monaco``, ...
    :param cluster_key: Recorded for later steps; SingleR labels cells individually.
    :returns: The same AnnData with ``obs['cell_type']`` and ``obs['annotation_score']``.
    :raises RuntimeError: R, SingleR or celldex is missing, or SingleR returns nothing.
    """
    key = _resolve_cluster_key(adata, cluster_key)
    return _remember(adata, key, _annotate_singler(adata, reference))


def annotate_scmap(adata, *, reference: str = "HPCA", cluster_key: str | None = None):
    """Per-cell labels projected with scmap onto a celldex atlas, run in R.

    :param reference: A celldex atlas. Default ``HPCA``.
    :param cluster_key: Recorded for later steps.
    :returns: The same AnnData with ``obs['cell_type']``.
    :raises RuntimeError: R, scmap or celldex is missing, or scmap returns nothing.
    """
    key = _resolve_cluster_key(adata, cluster_key)
    return _remember(adata, key, _annotate_scmap(adata, reference))


def annotate_scsa(adata, *, cluster_key: str | None = None, species: str = "Human", tissue: str = "All",
                  foldchange: float = 1.5, pvalue: float = 0.05):
    """Cluster labels from CellMarker 2.0 genes scored against each cluster's markers (SCSA).

    Runs a Wilcoxon test per cluster and scores each cell type's markers with a
    Fisher exact test. The CellMarker table downloads once to
    ``~/.cache/omicsclaw/scsa``; without network a small built-in set is used.

    :param cluster_key: As in :func:`annotate`.
    :param species: ``"Human"`` (default) or ``"Mouse"``.
    :param tissue: CellMarker tissue filter such as ``"Blood"``. Default ``"All"``.
    :param foldchange: Minimum fold change of a cluster marker. Default 1.5.
    :param pvalue: Maximum adjusted p-value of a cluster marker. Default 0.05.
    :returns: The same AnnData with ``obs['cell_type']``.
    """
    key = _resolve_cluster_key(adata, cluster_key)
    return _remember(adata, key, _annotate_scsa(adata, cluster_key=key, species=species, tissue=tissue,
                                                foldchange=foldchange, pvalue=pvalue))


def run_info(adata, *, keep: bool = True) -> dict:
    """What the last annotate function recorded: ``cluster_key`` and ``summary``.

    ``summary`` has ``requested_method``, ``actual_method``, ``used_fallback``,
    ``fallback_reason``, ``n_cell_types``, ``cell_type_counts`` and the method's
    own details (reference, marker source, ...).

    :param keep: Leave the record in ``adata.uns``; ``False`` removes it.
    :returns: The record, or an empty dict when no annotate function has run on *adata*.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def annotation_table(adata, *, key: str = "cell_type") -> pd.DataFrame:
    """Cells per cell type, largest first.

    :param key: The ``obs`` column with the labels. Default ``"cell_type"``.
    :returns: Columns ``cell_type``, ``n_cells`` and ``proportion_pct``.
    """
    counts = adata.obs[key].astype(str).value_counts()
    if counts.empty:
        return pd.DataFrame(columns=["cell_type", "n_cells"])
    df = pd.DataFrame({"cell_type": [str(k) for k in counts.index], "n_cells": [int(v) for v in counts.values]})
    df["proportion_pct"] = (df["n_cells"] / max(int(df["n_cells"].sum()), 1) * 100).round(2)
    return df.sort_values(["n_cells", "cell_type"], ascending=[False, True]).reset_index(drop=True)


def cluster_annotation_matrix(adata, *, cluster_key: str, key: str = "cell_type") -> pd.DataFrame:
    """For each cluster, the fraction of its cells given each label.

    :param cluster_key: The ``obs`` column with cluster labels.
    :param key: The ``obs`` column with cell-type labels. Default ``"cell_type"``.
    :returns: One row per cluster (first column named after *cluster_key*), one column per label;
        empty when either column is missing.
    """
    if cluster_key not in adata.obs.columns or key not in adata.obs.columns:
        return pd.DataFrame()
    matrix = pd.crosstab(adata.obs[cluster_key].astype(str), adata.obs[key].astype(str), normalize="index")
    matrix.index.name = cluster_key
    return matrix.reset_index()


def annotation_figure(adata, *, key: str = "cell_type", basis: str | None = None):
    """A scatter plot of the 2-D embedding coloured by cell type.

    :param key: The ``obs`` column to colour by. Default ``"cell_type"``.
    :param basis: The ``obsm`` key to plot. Default: the first of ``X_umap``, ``X_tsne``, ``X_pca``.
    :returns: A matplotlib Figure.
    :raises KeyError: no embedding is present.
    """
    import matplotlib.pyplot as plt

    name = basis or next((k for k in ("X_umap", "X_tsne", "X_pca") if k in adata.obsm), None)
    if name is None:
        raise KeyError("no embedding in obsm to plot")
    coords = np.asarray(adata.obsm[name])[:, :2]
    labels = adata.obs[key].astype(str)
    fig, ax = plt.subplots(figsize=(7, 5))
    palette = plt.get_cmap("tab20")
    for index, label in enumerate(labels.value_counts().index):
        mask = (labels == label).to_numpy()
        ax.scatter(coords[mask, 0], coords[mask, 1], s=4, color=palette(index % 20), label=label, linewidths=0)
    ax.set_xlabel(f"{name[2:]}1")
    ax.set_ylabel(f"{name[2:]}2")
    ax.set_title(f"{name[2:]} coloured by {key}")
    ax.legend(markerscale=3, fontsize=7, frameon=False, bbox_to_anchor=(1.0, 1.0), loc="upper left")
    fig.tight_layout()
    return fig


BUILTIN_MARKERS_HUMAN: dict[str, list[str]] = {
    # --- Blood / PBMC ---
    "CD4+ T cell": ["CD3D", "CD3E", "CD4", "IL7R"],
    "CD8+ T cell": ["CD3D", "CD3E", "CD8A", "CD8B"],
    "Regulatory T cell": ["FOXP3", "IL2RA", "CTLA4"],
    "B cell": ["MS4A1", "CD79A", "CD79B", "CD19"],
    "Plasma cell": ["MZB1", "SDC1", "IGHA1", "JCHAIN"],
    "NK cell": ["GNLY", "NKG7", "KLRD1", "NCAM1"],
    "CD14+ Monocyte": ["CD14", "LYZ", "S100A9", "S100A8"],
    "CD16+ Monocyte": ["FCGR3A", "MS4A7"],
    "Dendritic cell": ["FCER1A", "CD1C", "CLEC10A"],
    "Platelet": ["PPBP", "PF4"],
    # --- Brain ---
    "Neuron": ["SNAP25", "SYT1", "RBFOX3", "STMN2"],
    "Astrocyte": ["AQP4", "GFAP", "SLC1A3"],
    "Oligodendrocyte": ["MBP", "PLP1", "MOG"],
    "Microglia": ["CX3CR1", "P2RY12", "CSF1R"],
    "OPC": ["PDGFRA", "CSPG4", "OLIG2"],
    # --- General tissue / stroma ---
    "Epithelial": ["EPCAM", "KRT18", "KRT19"],
    "Fibroblast": ["COL1A1", "COL1A2", "DCN", "LUM"],
    "Endothelial": ["PECAM1", "VWF", "CDH5"],
    "Smooth muscle cell": ["ACTA2", "TAGLN", "MYH11"],
    "Macrophage": ["CD68", "CD163", "MRC1"],
    "Mast cell": ["KIT", "TPSAB1", "TPSB2"],
}


def _load_marker_file(path: str | Path) -> dict[str, list[str]]:
    """Load custom marker genes from a JSON or CSV file.

    JSON format::

        {"T cell": ["CD3D", "CD3E"], "B cell": ["MS4A1", "CD79A"]}

    CSV format (two columns, no header or header ``cell_type,markers``)::

        T cell,CD3D;CD3E;CD4
        B cell,MS4A1;CD79A
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Marker file not found: {p}")
    text = p.read_text(encoding="utf-8").strip()
    if p.suffix == ".json":
        markers = json.loads(text)
    else:
        markers: dict[str, list[str]] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.lower().startswith("cell_type"):
                continue
            parts = line.split(",", 1)
            if len(parts) != 2:
                continue
            cell_type = parts[0].strip().strip('"').strip("'")
            genes = [g.strip().strip('"').strip("'") for g in parts[1].replace(";", ",").split(",") if g.strip()]
            if cell_type and genes:
                markers[cell_type] = genes
    if not markers:
        raise ValueError(f"No valid marker entries found in {p}")
    return markers


def _detect_species_hint(var_names) -> str:
    """Heuristic species detection from gene naming convention.

    Human genes: UPPER (CD3D, MS4A1).  Mouse genes: Title case (Cd3d, Ms4a1).
    """
    sample = list(var_names[:min(500, len(var_names))])
    if not sample:
        return "unknown"
    upper_count = sum(1 for g in sample if g == g.upper())
    title_count = sum(1 for g in sample if g != g.upper() and g[0].isupper())
    ratio_upper = upper_count / len(sample)
    ratio_title = title_count / len(sample)
    if ratio_upper > 0.7:
        return "human"
    if ratio_title > 0.5:
        return "mouse"
    return "unknown"


def _build_case_insensitive_map(var_names) -> dict[str, str]:
    """Map UPPER gene names -> actual var_names for case-insensitive matching."""
    return {g.upper(): g for g in var_names}


# ---------------------------------------------------------------------------
# Method implementations
# ---------------------------------------------------------------------------


def _record_annotation_execution(
    adata,
    *,
    requested_method: str,
    actual_method: str,
    fallback_reason: str = "",
) -> None:
    adata.obs["annotation_requested_method"] = requested_method
    adata.obs["annotation_actual_method"] = actual_method
    adata.obs["annotation_method"] = actual_method
    adata.uns["annotation_runtime"] = {
        "requested_method": requested_method,
        "actual_method": actual_method,
        "used_fallback": bool(fallback_reason),
        "fallback_reason": fallback_reason,
    }


def _annotation_summary(
    adata,
    *,
    requested_method: str,
    actual_method: str,
    fallback_reason: str = "",
    expression_source: str | None = None,
) -> dict:
    counts = adata.obs["cell_type"].astype(str).value_counts().to_dict()
    summary = {
        "method": actual_method,
        "requested_method": requested_method,
        "actual_method": actual_method,
        "used_fallback": bool(fallback_reason),
        "fallback_reason": fallback_reason,
        "n_cell_types": len(counts),
        "cell_type_counts": {str(k): int(v) for k, v in counts.items()},
    }
    if expression_source:
        summary["expression_source"] = expression_source
    return summary


def _candidate_cluster_keys(adata) -> list[str]:
    matrix_contract = get_matrix_contract(adata)
    candidates: list[str] = []
    primary = matrix_contract.get("primary_cluster_key")
    if primary and primary in adata.obs.columns:
        candidates.append(str(primary))
    for key in ("leiden", "louvain", "seurat_clusters", "cluster", "cell_type"):
        if key in adata.obs.columns and key not in candidates:
            candidates.append(key)
    return candidates


def _resolve_cluster_key(adata, cluster_key: str | None) -> str | None:
    if cluster_key and cluster_key in adata.obs.columns:
        return cluster_key
    candidates = _candidate_cluster_keys(adata)
    return candidates[0] if candidates else None


def _annotate_markers(adata, markers=None, cluster_key: str = "leiden", marker_file: str | None = None):
    """Marker-based annotation with gene-overlap detection and species awareness."""
    # ---- 1. Resolve marker source ----
    if marker_file:
        markers = _load_marker_file(marker_file)
        marker_source = f"custom file: {marker_file}"
    elif markers is not None:
        marker_source = "caller-provided"
    else:
        markers = BUILTIN_MARKERS_HUMAN
        marker_source = "built-in (human, multi-tissue)"

    expression_source, expr = "adata.X", adata

    if cluster_key not in adata.obs:
        raise ValueError(
            f"Marker-based annotation requires an existing cluster/label column. "
            f"`{cluster_key}` was not found in adata.obs."
        )

    # ---- 2. Gene overlap diagnostic ----
    all_marker_genes = sorted({g for genes in markers.values() for g in genes})
    expr_var_names = set(expr.var_names)
    matched_genes = [g for g in all_marker_genes if g in expr_var_names]
    overlap_rate = len(matched_genes) / len(all_marker_genes) if all_marker_genes else 0.0

    case_remap: dict[str, str] | None = None
    species_hint = _detect_species_hint(expr.var_names)

    if overlap_rate == 0:
        # Attempt case-insensitive rescue (human markers vs mouse gene names)
        upper_map = _build_case_insensitive_map(expr.var_names)
        case_matched = [g for g in all_marker_genes if g.upper() in upper_map]
        if case_matched:
            case_remap = {g: upper_map[g.upper()] for g in all_marker_genes if g.upper() in upper_map}
            logger.warning(
                "0/%d marker genes matched by exact name, but %d/%d matched case-insensitively. "
                "Dataset appears to use %s gene naming (detected species: %s). "
                "Proceeding with case-insensitive matching.",
                len(all_marker_genes), len(case_matched), len(all_marker_genes),
                "Title-case" if species_hint == "mouse" else "non-UPPER",
                species_hint,
            )
        else:
            logger.warning(
                "NONE of the %d built-in marker genes were found in the dataset (%d genes). "
                "Detected species hint: %s. Marker source: %s.\n"
                "  This usually means the built-in markers do not match your tissue/organism.\n"
                "  Solutions:\n"
                "    1. Provide custom markers:  --marker-file markers.json\n"
                "    2. Use CellTypist:          --method celltypist --model <model_name>\n"
                "    3. Use reference mapping:    --method knnpredict --reference <ref.h5ad>\n"
                "  See SKILL.md 'Reference Data Guide' for download instructions.",
                len(all_marker_genes), len(expr_var_names), species_hint, marker_source,
            )
    elif overlap_rate < 0.3:
        logger.warning(
            "Only %d/%d (%.0f%%) marker genes found in the dataset. "
            "Annotation quality may be limited. Species hint: %s.",
            len(matched_genes), len(all_marker_genes), overlap_rate * 100, species_hint,
        )
    else:
        logger.info(
            "Marker gene overlap: %d/%d (%.0f%%). Species hint: %s. Source: %s.",
            len(matched_genes), len(all_marker_genes), overlap_rate * 100,
            species_hint, marker_source,
        )

    # ---- 3. Score each cluster ----
    cluster_annotations: dict[str, str] = {}
    cluster_scores: dict[str, float] = {}
    for cluster in adata.obs[cluster_key].astype(str).unique():
        cluster_mask = adata.obs[cluster_key].astype(str) == cluster
        cluster_data = adata[cluster_mask]

        best_type = "Unknown"
        best_score = 0.0
        for cell_type, marker_genes in markers.items():
            if case_remap:
                available = [case_remap[g] for g in marker_genes if g in case_remap]
            else:
                available = [g for g in marker_genes if g in expr_var_names]
            if not available:
                continue
            score = float(np.asarray(cluster_data[:, available].X.mean()).item())
            if score > best_score:
                best_score = score
                best_type = cell_type

        cluster_annotations[cluster] = best_type
        cluster_scores[cluster] = best_score

    # ---- 4. Detect all-Unknown and warn ----
    unknown_clusters = [c for c, t in cluster_annotations.items() if t == "Unknown"]
    if len(unknown_clusters) == len(cluster_annotations):
        logger.error(
            "ALL %d clusters were annotated as 'Unknown' — the markers did not match any genes "
            "in this dataset. This is almost certainly because the built-in markers are not "
            "appropriate for your tissue type or organism.\n"
            "  Recommended actions:\n"
            "    1. --marker-file markers.json   (provide tissue-specific markers)\n"
            "    2. --method celltypist --model <model>   (100+ pre-trained models)\n"
            "       Run: python -c \"import celltypist; celltypist.models.models_description()\" to list models\n"
            "    3. --method knnpredict --reference <ref.h5ad>   (your own labeled reference)\n"
            "  See SKILL.md 'Reference Data Guide' for details.",
            len(cluster_annotations),
        )
    elif unknown_clusters:
        logger.warning(
            "%d/%d clusters annotated as 'Unknown' (clusters: %s). "
            "Consider providing more specific markers via --marker-file.",
            len(unknown_clusters), len(cluster_annotations),
            ", ".join(unknown_clusters[:10]),
        )

    adata.obs["cell_type"] = adata.obs[cluster_key].astype(str).map(cluster_annotations)
    adata.obs["annotation_score"] = adata.obs[cluster_key].astype(str).map(cluster_scores).astype(float)
    _record_annotation_execution(
        adata,
        requested_method="markers",
        actual_method="markers",
    )
    logger.info(
        "Annotated %d clusters (%d cell types, %d Unknown). Marker source: %s.",
        len(cluster_annotations),
        len(set(cluster_annotations.values()) - {"Unknown"}),
        len(unknown_clusters),
        marker_source,
    )
    return _annotation_summary(
        adata,
        requested_method="markers",
        actual_method="markers",
        expression_source=expression_source,
    )


def _annotate_manual(adata, *, cluster_key: str, manual_map: str | None = None, manual_map_file: str | None = None):
    """Apply an explicit user-supplied cluster-to-label mapping."""
    if manual_map_file:
        annotations = sc_annotation_utils.load_manual_annotation_map(manual_map_file)
        mapping_source = str(manual_map_file)
    elif manual_map:
        annotations = sc_annotation_utils.parse_manual_annotation_map(manual_map)
        mapping_source = "inline"
    else:
        raise ValueError("Manual annotation requires --manual-map or --manual-map-file.")

    sc_annotation_utils.annotate_clusters_manual(
        adata,
        annotations=annotations,
        cluster_key=cluster_key,
        annotation_key="cell_type",
        inplace=True,
    )
    adata.obs["annotation_score"] = np.nan
    _record_annotation_execution(
        adata,
        requested_method="manual",
        actual_method="manual",
    )
    summary = _annotation_summary(
        adata,
        requested_method="manual",
        actual_method="manual",
        expression_source="manual_mapping",
    )
    summary["manual_mapping_source"] = mapping_source
    summary["manual_mapping"] = annotations
    return summary


def _annotate_celltypist(adata, model: str = "Immune_All_Low", majority_voting: bool = False):
    """CellTypist annotation with explicit fallback recording."""
    celltypist_input, expression_source = sc_annotation_utils.build_celltypist_input_adata(adata)
    is_valid, reason = sc_annotation_utils.validate_celltypist_input_matrix(celltypist_input)
    if not is_valid:
        logger.warning("CellTypist input validation failed: %s", reason)
        _annotate_markers(adata)
        _record_annotation_execution(
            adata,
            requested_method="celltypist",
            actual_method="markers",
            fallback_reason=reason,
        )
        summary = _annotation_summary(
            adata,
            requested_method="celltypist",
            actual_method="markers",
            fallback_reason=reason,
            expression_source=expression_source,
        )
        return summary

    try:
        model_name = model if model.endswith(".pkl") else f"{model}.pkl"
        sc_annotation_utils.annotate_with_celltypist(
            celltypist_input,
            model=model_name,
            majority_voting=majority_voting,
            annotation_key="cell_type",
            inplace=True,
        )
        adata.obs["cell_type"] = celltypist_input.obs["cell_type"].values
        if "cell_type_score" in celltypist_input.obs.columns:
            adata.obs["annotation_score"] = pd.to_numeric(celltypist_input.obs["cell_type_score"], errors="coerce").values
        if "cell_type_prob" in celltypist_input.obsm:
            adata.obsm["cell_type_prob"] = celltypist_input.obsm["cell_type_prob"]
        _record_annotation_execution(
            adata,
            requested_method="celltypist",
            actual_method="celltypist",
        )
        return _annotation_summary(
            adata,
            requested_method="celltypist",
            actual_method="celltypist",
            expression_source=expression_source,
        )
    except Exception as exc:
        reason = str(exc)
        logger.warning("CellTypist annotation unavailable (%s); falling back to marker-based annotation", exc)
        _annotate_markers(adata)
        _record_annotation_execution(
            adata,
            requested_method="celltypist",
            actual_method="markers",
            fallback_reason=reason,
        )
        summary = _annotation_summary(
            adata,
            requested_method="celltypist",
            actual_method="markers",
            fallback_reason=reason,
            expression_source=expression_source,
        )
    return summary


def _annotate_popv(adata, reference: str = "HPCA", cluster_key: str = "leiden"):
    """PopV-style reference mapping with cluster consensus."""
    metadata = sc_annotation_utils.apply_popv_annotation(
        adata,
        reference,
        cluster_key=cluster_key,
    )
    actual_method = metadata.get("backend", "popv")
    _record_annotation_execution(
        adata,
        requested_method="popv",
        actual_method=actual_method,
    )
    summary = _annotation_summary(
        adata,
        requested_method="popv",
        actual_method=actual_method,
        expression_source=metadata.get("expression_source"),
    )
    summary.update(
        {
            "backend": metadata.get("backend"),
            "reference": reference,
            "reference_label_key": metadata.get("reference_label_key"),
            "reference_cell_types": metadata.get("reference_cell_types"),
            "reference_gene_overlap": metadata.get("reference_gene_overlap"),
            "reference_path": metadata.get("reference_path"),
            "popv_methods": metadata.get("popv_methods"),
        }
    )
    return summary


def _annotate_knnpredict(adata, reference: str = "HPCA", cluster_key: str = "leiden"):
    """Lightweight reference mapping inspired by SCOP KNNPredict."""
    metadata = sc_annotation_utils.apply_knnpredict_annotation(
        adata,
        reference,
        cluster_key=cluster_key,
    )
    _record_annotation_execution(
        adata,
        requested_method="knnpredict",
        actual_method="knnpredict",
    )
    summary = _annotation_summary(
        adata,
        requested_method="knnpredict",
        actual_method="knnpredict",
        expression_source=metadata.get("expression_source"),
    )
    summary.update(
        {
            "backend": metadata.get("backend"),
            "reference": reference,
            "reference_label_key": metadata.get("reference_label_key"),
            "reference_cell_types": metadata.get("reference_cell_types"),
            "reference_gene_overlap": metadata.get("reference_gene_overlap"),
            "reference_path": metadata.get("reference_path"),
        }
    )
    return summary


def _apply_r_annotations(adata, df: pd.DataFrame, *, requested_method: str, actual_method: str) -> dict:
    df = df.copy()
    if df.empty:
        raise RuntimeError(f"R annotation method '{requested_method}' returned no predictions")
    df.index = df.index.astype(str)
    df = df.reindex(adata.obs_names)
    labels = df["pruned_label"].fillna(df["cell_type"]).astype(str)
    adata.obs["cell_type"] = labels.values
    if "score" in df.columns:
        adata.obs["annotation_score"] = pd.to_numeric(df["score"], errors="coerce").values
    _record_annotation_execution(
        adata,
        requested_method=requested_method,
        actual_method=actual_method,
    )
    return _annotation_summary(adata, requested_method=requested_method, actual_method=actual_method)


def _annotate_singler(adata, reference: str = "HPCA"):
    """SingleR annotation via the shared R bridge."""
    validate_r_environment(required_r_packages=["SingleR", "celldex", "SingleCellExperiment", "zellkonverter"])
    export_adata, expression_source = sc_annotation_utils.build_celltypist_input_adata(adata)
    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_singler_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        r_home = tmpdir / "r_home"
        xdg_cache = tmpdir / "xdg_cache"
        eh_cache = tmpdir / "experimenthub"
        for path in (r_home, xdg_cache, eh_cache):
            path.mkdir(parents=True, exist_ok=True)
        export_adata.write_h5ad(input_h5ad)
        runner.run_script(
            "sc_singler_annotate.R",
            args=[str(input_h5ad), str(output_dir), reference],
            expected_outputs=["singler_results.csv"],
            output_dir=output_dir,
            env={
                "HOME": str(r_home),
                "XDG_CACHE_HOME": str(xdg_cache),
                "OMICSCLAW_EXPERIMENTHUB_CACHE": str(eh_cache),
                "ZELLKONVERTER_USE_BASILISK": "FALSE",
            },
        )
        df = pd.read_csv(output_dir / "singler_results.csv", index_col=0)
    summary = _apply_r_annotations(adata, df, requested_method="singler", actual_method="singler")
    summary["expression_source"] = expression_source
    summary["reference"] = reference
    return summary


def _annotate_scmap(adata, reference: str = "HPCA"):
    """scmap annotation via the shared R bridge."""
    validate_r_environment(required_r_packages=["scmap", "celldex", "SingleCellExperiment", "zellkonverter"])
    export_adata, expression_source = sc_annotation_utils.build_celltypist_input_adata(adata)
    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_scmap_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        r_home = tmpdir / "r_home"
        xdg_cache = tmpdir / "xdg_cache"
        eh_cache = tmpdir / "experimenthub"
        for path in (r_home, xdg_cache, eh_cache):
            path.mkdir(parents=True, exist_ok=True)
        export_adata.write_h5ad(input_h5ad)
        runner.run_script(
            "sc_scmap_annotate.R",
            args=[str(input_h5ad), str(output_dir), reference],
            expected_outputs=["scmap_results.csv"],
            output_dir=output_dir,
            env={
                "HOME": str(r_home),
                "XDG_CACHE_HOME": str(xdg_cache),
                "OMICSCLAW_EXPERIMENTHUB_CACHE": str(eh_cache),
                "ZELLKONVERTER_USE_BASILISK": "FALSE",
            },
        )
        df = pd.read_csv(output_dir / "scmap_results.csv", index_col=0)
    summary = _apply_r_annotations(adata, df, requested_method="scmap", actual_method="scmap")
    summary["expression_source"] = expression_source
    summary["reference"] = reference
    return summary


def _annotate_scsa(
    adata,
    cluster_key: str = "leiden",
    species: str = "Human",
    tissue: str = "All",
    foldchange: float = 1.5,
    pvalue: float = 0.05,
):
    """SCSA-style annotation: marker DE -> CellMarker database Fisher exact test scoring.

    Adapted from pySCSA (Cao et al.). Runs Wilcoxon DE per cluster, then scores
    each cluster against the CellMarker database using Fisher's exact test and
    Z-score ranking.
    """
    from scipy.stats import fisher_exact

    if cluster_key not in adata.obs.columns:
        raise ValueError(
            f"SCSA requires a cluster column. '{cluster_key}' not found in adata.obs."
        )

    # ---- 1. Run Wilcoxon DE to get markers per cluster ----
    logger.info("SCSA: running Wilcoxon DE for cluster markers (key=%s)", cluster_key)
    sc.tl.rank_genes_groups(adata, cluster_key, method="wilcoxon", use_raw=False)
    result = adata.uns["rank_genes_groups"]
    groups = result["names"].dtype.names

    # Extract significant markers per cluster
    cluster_markers: dict[str, list[str]] = {}
    for group in groups:
        names = result["names"][group]
        logfcs = result["logfoldchanges"][group]
        pvals = result["pvals_adj"][group]
        sig_genes = []
        for name, lfc, pval in zip(names, logfcs, pvals):
            if abs(float(lfc)) >= foldchange and float(pval) <= pvalue:
                sig_genes.append(str(name))
        cluster_markers[str(group)] = sig_genes

    # ---- 2. Load or build CellMarker database ----
    cellmarker_db = _load_scsa_cellmarker_db(species=species, tissue=tissue)
    if not cellmarker_db:
        logger.error(
            "SCSA: CellMarker database is empty for species=%s, tissue=%s. "
            "This means no cell type entries matched. Try:\n"
            "  1. --species Human or --species Mouse\n"
            "  2. --tissue All (to search all tissues)\n"
            "  3. --method markers (with custom --marker-file)\n",
            species, tissue,
        )
        # Fall back to Unknown
        adata.obs["cell_type"] = "Unknown"
        adata.obs["annotation_score"] = 0.0
        _record_annotation_execution(adata, requested_method="scsa", actual_method="scsa")
        return _annotation_summary(adata, requested_method="scsa", actual_method="scsa")

    # ---- 3. Score each cluster using Fisher exact test ----
    all_detected_genes = set(adata.var_names)
    n_total_genes = len(all_detected_genes)

    cluster_annotations: dict[str, str] = {}
    cluster_scores: dict[str, float] = {}

    for cluster_id, sig_genes in cluster_markers.items():
        sig_set = set(sig_genes) & all_detected_genes
        if not sig_set:
            cluster_annotations[cluster_id] = "Unknown"
            cluster_scores[cluster_id] = 0.0
            continue

        best_type = "Unknown"
        best_zscore = -np.inf
        n_sig = len(sig_set)

        for cell_type, db_genes in cellmarker_db.items():
            db_set = set(db_genes) & all_detected_genes
            if not db_set:
                continue

            # Overlap between cluster markers and cell-type markers
            overlap = sig_set & db_set
            n_overlap = len(overlap)
            if n_overlap == 0:
                continue

            # Fisher exact test (one-sided, greater)
            n_db = len(db_set)
            contingency = [
                [n_overlap, n_sig - n_overlap],
                [n_db - n_overlap, n_total_genes - n_sig - n_db + n_overlap],
            ]
            # Ensure no negative values
            contingency = [[max(0, x) for x in row] for row in contingency]
            try:
                _, p_val = fisher_exact(contingency, alternative="greater")
            except Exception:
                continue

            # Convert to Z-score-like measure: -log10(p) * sign(enrichment)
            zscore = -np.log10(max(p_val, 1e-300)) * (n_overlap / max(n_sig, 1))

            if zscore > best_zscore:
                best_zscore = zscore
                best_type = cell_type

        cluster_annotations[cluster_id] = best_type
        cluster_scores[cluster_id] = float(best_zscore) if best_zscore > -np.inf else 0.0

    # ---- 4. Apply annotations ----
    adata.obs["cell_type"] = adata.obs[cluster_key].astype(str).map(cluster_annotations)
    adata.obs["annotation_score"] = adata.obs[cluster_key].astype(str).map(cluster_scores).astype(float)
    _record_annotation_execution(adata, requested_method="scsa", actual_method="scsa")

    # ---- 5. Detect degenerate output ----
    unknown_clusters = [c for c, t in cluster_annotations.items() if t == "Unknown"]
    if len(unknown_clusters) == len(cluster_annotations):
        logger.error(
            "  *** ALL %d clusters were labeled 'Unknown' by SCSA. ***\n"
            "  This usually means no marker genes overlapped with the CellMarker database.\n"
            "  How to fix:\n"
            "    Option 1 -- Adjust DE thresholds:\n"
            "      --scsa-foldchange 1.0 --scsa-pvalue 0.1\n"
            "    Option 2 -- Widen tissue filter:\n"
            "      --tissue All --species Human\n"
            "    Option 3 -- Use a different method:\n"
            "      --method markers --marker-file custom_markers.json\n"
            "      --method celltypist --model <model>.pkl",
            len(cluster_annotations),
        )
    elif unknown_clusters:
        logger.warning(
            "SCSA: %d/%d clusters annotated as 'Unknown' (clusters: %s).",
            len(unknown_clusters), len(cluster_annotations),
            ", ".join(unknown_clusters[:10]),
        )

    logger.info(
        "SCSA: annotated %d clusters (%d cell types, %d Unknown). "
        "Species=%s, tissue=%s.",
        len(cluster_annotations),
        len(set(cluster_annotations.values()) - {"Unknown"}),
        len(unknown_clusters),
        species, tissue,
    )
    return _annotation_summary(
        adata,
        requested_method="scsa",
        actual_method="scsa",
        expression_source="adata.X",
    )


def _load_scsa_cellmarker_db(
    species: str = "Human",
    tissue: str = "All",
) -> dict[str, list[str]]:
    """Load a CellMarker-style database for SCSA annotation.

    Downloads and caches CellMarker2.0 data, then filters by species/tissue.
    Returns dict mapping cell_type -> list of marker gene symbols.
    """
    cache_dir = Path.home() / ".cache" / "omicsclaw" / "scsa"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "cellmarker2_markers.csv"

    if not db_path.exists():
        logger.info("SCSA: downloading CellMarker 2.0 database...")
        try:
            _download_cellmarker_db(db_path)
        except Exception as exc:
            logger.warning("Failed to download CellMarker database: %s", exc)
            logger.info("SCSA: falling back to built-in compact marker database.")
            return _builtin_scsa_markers(species)

    # Parse the database
    try:
        db_df = pd.read_csv(db_path, sep=",", encoding="utf-8", on_bad_lines="skip")
    except Exception:
        try:
            db_df = pd.read_csv(db_path, sep="\t", encoding="utf-8", on_bad_lines="skip")
        except Exception as exc:
            logger.warning("Failed to parse CellMarker database: %s", exc)
            return _builtin_scsa_markers(species)

    # Detect column names (CellMarker 2.0 format)
    species_col = None
    tissue_col = None
    celltype_col = None
    marker_col = None

    for col in db_df.columns:
        col_lower = col.lower().strip()
        if "species" in col_lower or "specie" in col_lower:
            species_col = col
        elif "tissue" in col_lower and "sub" not in col_lower:
            tissue_col = col
        elif "cell_name" in col_lower or "cell_type" in col_lower or col_lower == "cellname" or "cell name" in col_lower:
            celltype_col = col
        elif "marker" in col_lower or "symbol" in col_lower or "gene" in col_lower:
            marker_col = col

    if not celltype_col or not marker_col:
        logger.warning(
            "SCSA: CellMarker CSV columns not recognized (%s). Using built-in markers.",
            list(db_df.columns),
        )
        return _builtin_scsa_markers(species)

    # Filter by species
    if species_col:
        species_norm = species.strip().lower()
        db_df = db_df[db_df[species_col].astype(str).str.lower().str.contains(species_norm, na=False)]

    # Filter by tissue
    if tissue_col and tissue.lower() != "all":
        tissue_norm = tissue.strip().lower()
        db_df = db_df[db_df[tissue_col].astype(str).str.lower().str.contains(tissue_norm, na=False)]

    # Build marker dict
    result: dict[str, list[str]] = {}
    for _, row in db_df.iterrows():
        ct = str(row[celltype_col]).strip()
        markers_raw = str(row[marker_col]).strip()
        if not ct or ct == "nan" or not markers_raw or markers_raw == "nan":
            continue
        # Markers can be comma-separated, semicolon-separated, or space-separated
        genes = [g.strip() for g in markers_raw.replace(";", ",").replace("/", ",").split(",") if g.strip()]
        if ct in result:
            result[ct].extend(genes)
        else:
            result[ct] = genes

    # Deduplicate
    for ct in result:
        result[ct] = list(set(result[ct]))

    logger.info("SCSA: loaded %d cell types from CellMarker database.", len(result))
    return result


def _download_cellmarker_db(db_path: Path) -> None:
    """Download CellMarker 2.0 database."""
    import urllib.request

    urls = [
        "http://bio-bigdata.hrbmu.edu.cn/CellMarker/CellMarker_download_files/file/Cell_marker_All.csv",
        "http://117.50.127.228/CellMarker/CellMarker_download_files/file/Cell_marker_All.csv",
    ]

    for url in urls:
        try:
            logger.info("  Trying %s ...", url)
            urllib.request.urlretrieve(url, str(db_path))
            if db_path.exists() and db_path.stat().st_size > 1000:
                logger.info("  Download successful: %s (%d bytes)", db_path, db_path.stat().st_size)
                return
        except Exception as exc:
            logger.warning("  Failed: %s", exc)
            continue

    raise RuntimeError(
        "Could not download CellMarker database from any URL.\n"
        "  Please download manually from http://bio-bigdata.hrbmu.edu.cn/CellMarker/\n"
        "  and place it at: %s" % db_path
    )


def _builtin_scsa_markers(species: str = "Human") -> dict[str, list[str]]:
    """Compact built-in markers as fallback when CellMarker DB is unavailable."""
    if species.lower() in ("mouse", "mm", "mus musculus"):
        # Mouse markers in Title case
        return {
            "T cell": ["Cd3d", "Cd3e", "Cd3g"],
            "B cell": ["Cd79a", "Cd79b", "Ms4a1", "Cd19"],
            "NK cell": ["Nkg7", "Klrb1c", "Gzma"],
            "Monocyte": ["Cd14", "Lyz2", "Csf1r"],
            "Macrophage": ["Cd68", "Adgre1", "Mrc1"],
            "Dendritic cell": ["Itgax", "Flt3", "H2-Aa"],
            "Neutrophil": ["S100a8", "S100a9", "Ly6g"],
            "Epithelial": ["Epcam", "Krt18", "Krt19"],
            "Fibroblast": ["Col1a1", "Col1a2", "Dcn"],
            "Endothelial": ["Pecam1", "Cdh5", "Vwf"],
        }
    # Human markers (UPPER)
    return {
        "T cell": ["CD3D", "CD3E", "CD3G", "CD2"],
        "CD4+ T cell": ["CD3D", "CD4", "IL7R"],
        "CD8+ T cell": ["CD3D", "CD8A", "CD8B"],
        "B cell": ["CD79A", "CD79B", "MS4A1", "CD19"],
        "Plasma cell": ["MZB1", "SDC1", "IGHA1", "JCHAIN"],
        "NK cell": ["GNLY", "NKG7", "KLRD1", "NCAM1"],
        "CD14+ Monocyte": ["CD14", "LYZ", "S100A9", "S100A8"],
        "CD16+ Monocyte": ["FCGR3A", "MS4A7"],
        "Macrophage": ["CD68", "CD163", "MRC1"],
        "Dendritic cell": ["FCER1A", "CD1C", "CLEC10A"],
        "Mast cell": ["KIT", "TPSAB1", "TPSB2"],
        "Platelet": ["PPBP", "PF4"],
        "Neutrophil": ["S100A8", "S100A9", "FCGR3B", "CSF3R"],
        "Epithelial": ["EPCAM", "KRT18", "KRT19"],
        "Fibroblast": ["COL1A1", "COL1A2", "DCN", "LUM"],
        "Endothelial": ["PECAM1", "VWF", "CDH5"],
        "Smooth muscle cell": ["ACTA2", "TAGLN", "MYH11"],
        "Neuron": ["SNAP25", "SYT1", "RBFOX3"],
        "Astrocyte": ["AQP4", "GFAP", "SLC1A3"],
        "Oligodendrocyte": ["MBP", "PLP1", "MOG"],
        "Microglia": ["CX3CR1", "P2RY12", "CSF1R"],
    }
