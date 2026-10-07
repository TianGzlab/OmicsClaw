"""Discrete spatial cell labels from markers or reference mapping."""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from scipy import sparse
from skills.spatial._lib.annotation import (
    annotate_marker_based, annotate_tangram, annotate_scanvi,
    annotate_cellassign, get_default_signatures,
)
from skills.spatial._lib.adata_utils import require_spatial_coords

__all__ = ["annotate", "run_info", "cell_type_counts", "annotation_figure"]
_RUN_KEY = "omicsclaw_spatial_annotation_run"


def _validate_counts(data, layer):
    if layer is not None and layer in data.layers:
        matrix = data.layers[layer]
    elif layer in (None, "counts") and "counts" in data.layers:
        matrix = data.layers["counts"]
    elif layer in (None, "counts") and data.raw is not None:
        matrix = data.raw[:, data.var_names].X
    elif layer is None:
        matrix = data.X
    else:
        raise ValueError(f"Raw counts layer {layer!r} is required")
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if not np.isfinite(values).all() or (values < 0).any() or not np.allclose(values, np.round(values)):
        raise ValueError("scANVI and CellAssign require nonnegative integer raw counts")


def annotate(adata, *, method: str = "marker_based", reference=None,
             species: str = "human", marker_genes: dict | None = None,
             random_state: int = 0, **parameters):
    """Annotate in place and return the same AnnData without file writes.

    Marker and Tangram methods read log-normalized X. scANVI/CellAssign
    require raw counts in the requested layer (normally counts), raw, or
    explicitly selected X. Reference AnnData is copied before training.

    :param adata: Spatial AnnData with normalized X and method-required labels/counts.
    :param method: CLI default marker_based; tangram, scanvi or cellassign are optional.
    :param reference: Labelled reference AnnData for Tangram/scANVI; None otherwise.
    :param species: Human by default or mouse for built-in marker dictionaries.
    :param marker_genes: Optional CellAssign marker mapping; None uses species markers.
    :param random_state: Training seed, 0 by default; change to assess sensitivity.
    :param parameters: Method keyword options in references/parameters.md. Defaults
        match the CLI, including cluster_key=leiden and n_marker_genes=50.
    :returns: The same AnnData with cell_type labels and JSON run diagnostics.
    :raises ValueError: Invalid method, species, missing reference or invalid counts.
    :raises TypeError: Unknown method parameter.
    :raises ImportError: Missing backend; use install_skill_deps for the named package.
    """
    methods = {"marker_based": annotate_marker_based, "tangram": annotate_tangram,
               "scanvi": annotate_scanvi, "cellassign": annotate_cellassign}
    if method not in methods:
        raise ValueError(f"Unknown annotation method {method!r}")
    if species not in {"human", "mouse"}:
        raise ValueError("species must be human or mouse")
    if method in {"tangram", "scanvi"} and reference is None:
        raise ValueError(f"reference AnnData is required for {method}")
    if "reference_path" in parameters:
        raise ValueError("Pass reference AnnData, loaded with read_input, instead of reference_path")
    if method == "marker_based":
        parameters["species"] = species
        parameters["random_state"] = random_state
    elif method in {"tangram", "scanvi"}:
        parameters["reference"] = reference
    if method == "cellassign":
        parameters["marker_genes"] = get_default_signatures(species) if marker_genes is None else marker_genes
        parameters.setdefault("max_epochs", 400)
        parameters.setdefault("layer", "counts")
    if method in {"scanvi", "cellassign"}:
        layer = parameters.get("layer", "counts" if method == "scanvi" else None)
        _validate_counts(adata, layer)
        if reference is not None:
            _validate_counts(reference, layer)
    if method == "tangram":
        parameters["random_state"] = random_state
    try:
        if method in {"scanvi", "cellassign"}:
            import scvi
            scvi.settings.seed = random_state
        summary = methods[method](adata, **parameters)
    except ImportError as exc:
        raise ImportError(f"{exc}; use install_skill_deps for spatial-annotate (scvi-tools or tangram-sc)") from exc
    summary["random_state"] = random_state
    adata.uns[_RUN_KEY] = json.dumps(summary, default=lambda value: value.item())
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read annotation counts, method parameters and cluster-marker scores.

    :param adata: AnnData returned by annotate.
    :param keep: True retains diagnostics; False removes them before CLI serialization.
    :returns: Diagnostic dict, or an empty dict before analysis.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def cell_type_counts(adata):
    """Count cell labels and their percentages.

    :param adata: AnnData with cell_type labels; expression values are not read.
    :returns: DataFrame with cell_type, n_cells and proportion (percent).
    :raises KeyError: Annotation labels are absent.
    """
    counts = adata.obs["cell_type"].value_counts()
    return pd.DataFrame({"cell_type": counts.index.astype(str), "n_cells": counts.to_numpy(),
                         "proportion": np.round(counts.to_numpy() / adata.n_obs * 100, 2)})


def annotation_figure(adata):
    """Plot discrete cell labels in spatial coordinates.

    :param adata: Annotated spatial AnnData; reads coordinates and cell_type.
    :returns: A matplotlib Figure without saving it.
    :raises KeyError: Annotation labels are absent.
    """
    import matplotlib.pyplot as plt
    coords = np.asarray(adata.obsm[require_spatial_coords(adata)])
    labels = adata.obs["cell_type"].astype(str)
    fig, ax = plt.subplots()
    for label in sorted(labels.unique()):
        mask = (labels == label).to_numpy()
        ax.scatter(coords[mask, 0], coords[mask, 1], label=label, s=10)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.legend()
    return fig
