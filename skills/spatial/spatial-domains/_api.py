"""Spatial domain identification on expression and coordinate graphs."""
from __future__ import annotations

import json
import inspect
import numpy as np
import pandas as pd
import scanpy as sc
from skills.spatial._lib.domains import dispatch_method, refine_spatial_domains, SUPPORTED_METHODS
from skills.spatial._lib.adata_utils import require_spatial_coords
from skills.spatial._lib import domains as _backends

__all__ = ["identify", "run_info", "domain_counts", "domain_figure"]
_RUN_KEY = "omicsclaw_spatial_domains_run"


def identify(adata, *, method: str = "leiden", resolution: float = 1.0,
             spatial_weight: float = 0.3, refine: bool = False,
             random_state: int = 0, **parameters):
    """Identify domains in place and return the same AnnData.

    Reads log-normalized X, X_pca and spatial coordinates; graph methods reuse
    existing expression neighbors. SpaGCN, STAGATE and BANKSY results vary
    between runs because their training wrappers do not expose every RNG.

    :param adata: Preprocessed spatial AnnData; expression values are retained.
    :param method: CLI default leiden, or louvain/spagcn/stagate/graphst/banksy/cellcharter.
    :param resolution: Graph-clustering resolution, CLI default 1.0.
    :param spatial_weight: Spatial graph weight for Leiden/Louvain, CLI default 0.3.
    :param refine: False by default; True smooths labels using spatial KNN.
    :param random_state: Seed for PCA, graph clustering and supported backend seeds;
        0 for graph methods. The neural CLI wrappers historically use 42.
    :param parameters: Backend options listed in references/parameters.md;
        fixed-K methods use n_domains=7 unless supplied.
    :returns: The same AnnData with spatial_domain and JSON run diagnostics.
    :raises ValueError: Unsupported method or invalid graph parameters.
    :raises ImportError: A backend is missing; use install_skill_deps with the named package.
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method {method!r}")
    known = {"data_type"}
    for name in SUPPORTED_METHODS:
        known.update(inspect.signature(getattr(_backends, f"identify_domains_{name}")).parameters)
    unknown = set(parameters) - known
    if unknown:
        raise TypeError(f"Unknown domain parameters: {sorted(unknown)}")
    if "random_seed" in parameters:
        raise TypeError("Use random_state to select the backend seed")
    if not np.isfinite(resolution) or resolution <= 0 or not 0 <= spatial_weight <= 1:
        raise ValueError("resolution must be positive and spatial_weight in [0, 1]")
    if "X_pca" not in adata.obsm:
        sc.pp.pca(adata, random_state=random_state)
    if method in {"leiden", "louvain"} and "neighbors" not in adata.uns:
        sc.pp.neighbors(adata, n_neighbors=parameters.get("n_neighbors", 15),
                        n_pcs=min(parameters.get("n_pcs", 50), 30), random_state=random_state)
    if method in {"spagcn", "stagate", "graphst"} or (method == "cellcharter" and not parameters.get("auto_k", False)):
        if parameters.get("n_domains") is None:
            parameters["n_domains"] = 7
    if method in {"spagcn", "stagate", "graphst"}:
        parameters.setdefault("epochs", 100)
    try:
        summary = dispatch_method(method, adata, resolution=resolution,
                                  spatial_weight=spatial_weight, random_state=random_state,
                                  random_seed=random_state, **parameters)
    except ImportError as exc:
        raise ImportError(f"{exc}; use install_skill_deps for spatial-domains") from exc
    if refine:
        adata.obs["spatial_domain"] = pd.Categorical(refine_spatial_domains(adata))
        summary["domain_counts"] = adata.obs["spatial_domain"].value_counts().to_dict()
        summary["n_domains"] = int(adata.obs["spatial_domain"].nunique())
        summary["refined"] = True
    summary["random_state"] = random_state
    adata.uns[_RUN_KEY] = json.dumps(summary, default=lambda value: value.item())
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the method, domain sizes and refinement status.

    :param adata: AnnData returned by identify.
    :param keep: True retains diagnostics; False removes them before CLI serialization.
    :returns: Diagnostic dict, or an empty dict before analysis.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def domain_counts(adata):
    """Count observations and percentages per domain.

    :param adata: AnnData with spatial_domain labels; X is not read.
    :returns: DataFrame with domain, n_cells and proportion (percent).
    :raises KeyError: Domain labels are absent.
    """
    counts = adata.obs["spatial_domain"].value_counts()
    return pd.DataFrame({"domain": counts.index.astype(str), "n_cells": counts.to_numpy(),
                         "proportion": np.round(counts.to_numpy() / adata.n_obs * 100, 2)})


def domain_figure(adata):
    """Plot domain labels in spatial coordinates.

    :param adata: AnnData with spatial_domain and spatial coordinates; X is not read.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: Domain labels are absent.
    """
    import matplotlib.pyplot as plt
    coords = np.asarray(adata.obsm[require_spatial_coords(adata)])
    fig, ax = plt.subplots()
    labels = adata.obs["spatial_domain"].astype(str)
    for label in sorted(labels.unique()):
        mask = (labels == label).to_numpy()
        ax.scatter(coords[mask, 0], coords[mask, 1], label=label, s=10)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.legend()
    return fig
