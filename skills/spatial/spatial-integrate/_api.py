"""Batch integration without file I/O or report generation."""

from __future__ import annotations

import json
import numpy as np
import pandas as pd

from skills.spatial._lib.integration import SUPPORTED_METHODS, run_integration

__all__ = ["integrate", "run_info", "mixing_table", "embedding_figure"]
_RUN_KEY = "omicsclaw_spatial_integrate_run"


def integrate(adata, *, method: str = "harmony", batch_key: str = "batch",
              random_state: int = 0, **parameters):
    """Integrate a multi-batch PCA representation in place, preserving expression.

    :param adata: Preprocessed AnnData with X_pca and batch labels.
    :param method: harmony (default), bbknn (graph only), or scanorama.
    :param batch_key: Batch column in obs, default batch.
    :param random_state: Seed for Harmony, neighbors, UMAP and Leiden, default 0.
        BBKNN's default Annoy backend and Scanorama expose no seed here;
        their matching can vary across backend versions.
    :param parameters: Method keywords with original CLI defaults: Harmony
        theta=2, lamb=1, max_iter_harmony=10; BBKNN neighbors_within_batch=3,
        n_pcs=50, trim=None; Scanorama knn=20, sigma=15, alpha=0.1, batch_size=5000.
    :returns: The same AnnData with corrected embedding or graph, UMAP snapshots,
        per-spot batch entropy, and JSON run diagnostics. X is unchanged.
    :raises ValueError: Unknown method, missing batches/PCA, or invalid parameters.
    :raises ImportError: Missing backend; use install_skill_deps for that method.
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown integration method: {method}")
    allowed = {
        "harmony": {"theta", "lamb", "max_iter_harmony"},
        "bbknn": {"neighbors_within_batch", "n_pcs", "trim"},
        "scanorama": {"knn", "sigma", "alpha", "batch_size"},
    }[method]
    if parameters.keys() - allowed:
        raise ValueError(f"Unsupported {method} parameters: {sorted(parameters.keys() - allowed)}")
    for key, value in parameters.items():
        if key == "trim" and value is None:
            continue
        lower = 0 if key in {"theta", "alpha", "trim"} else 1
        if key in {"sigma", "lamb"}:
            valid = np.isfinite(value) and (value > 0 or (key == "lamb" and value == -1))
        else:
            valid = np.isfinite(value) and value >= lower
        if not valid:
            raise ValueError(f"Invalid {key}: {value}")
    try:
        summary = run_integration(adata, method=method, batch_key=batch_key,
                                  random_state=random_state, **parameters)
    except ImportError as exc:
        package = {"harmony": "harmonypy", "bbknn": "bbknn", "scanorama": "scanorama"}[method]
        raise ImportError(f"{method} needs {package}; use install_skill_deps for spatial-integrate. {exc}") from exc
    adata.uns[_RUN_KEY] = json.dumps({**summary, "random_state": random_state})
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the last integration summary.

    :param adata: AnnData returned by integrate.
    :param keep: True retains diagnostics; False removes them for CLI serialization.
    :returns: Summary including seed and effective method parameters, or an empty dict.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def mixing_table(adata) -> pd.DataFrame:
    """Return per-spot entropy before and after correction.

    :param adata: Integrated AnnData.
    :returns: observation, batch_entropy_before, batch_entropy_after and batch_entropy_delta.
    :raises KeyError: Integration entropy columns are absent.
    """
    table = adata.obs[["batch_entropy_before", "batch_entropy_after", "batch_entropy_delta"]].copy()
    table.insert(0, "observation", adata.obs_names.astype(str))
    return table.reset_index(drop=True)


def embedding_figure(adata, *, batch_key: str = "batch"):
    """Compare the pre- and post-integration UMAP coordinates.

    :param adata: Integrated AnnData with both UMAP snapshots.
    :param batch_key: Batch labels used for color, default batch.
    :returns: A matplotlib Figure; the caller saves and closes it.
    :raises KeyError: Batch labels or UMAP snapshots are absent.
    """
    import matplotlib.pyplot as plt

    labels = pd.Categorical(adata.obs[batch_key])
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, stage in zip(axes, ("before", "after")):
        coords = adata.obsm[f"X_umap_{stage}_integration"]
        for i, label in enumerate(labels.categories):
            mask = labels.codes == i
            ax.scatter(coords[mask, 0], coords[mask, 1], s=8, label=str(label))
        ax.set(title=stage, xlabel="UMAP 1", ylabel="UMAP 2")
    axes[-1].legend(title=batch_key)
    fig.tight_layout()
    return fig
