"""Register spatial slices and inspect their coordinate displacement."""

from __future__ import annotations

import json
import numpy as np
import pandas as pd

from skills.spatial._lib.adata_utils import require_spatial_coords
from skills.spatial._lib.register import detect_slice_key, run_registration

__all__ = ["register", "run_info", "shift_table", "registration_figure"]
_RUN_KEY = "omicsclaw_spatial_register_run"


def register(adata, *, method: str = "paste", slice_key: str | None = None,
             reference_slice: str | None = None, **parameters):
    """Add aligned coordinates in place without overwriting the input coordinates.

    :param adata: AnnData with expression, spatial coordinates and slice labels.
    :param method: paste (default) for transport or stalign for two-slice LDDMM.
    :param slice_key: Observation column; None detects slice, sample, section or batch.
    :param reference_slice: Target label; None uses the first sorted label.
    :param parameters: PASTE alpha=0.1, dissimilarity='kl', use_gpu=False;
        STalign image_size=(400,400), niter=2000, a=500, use_expression=False.
        PASTE is deterministic on CPU; STalign has no seed control and may vary.
    :returns: The same AnnData with spatial_aligned and JSON run diagnostics.
    :raises ValueError: Invalid labels, coordinates, method or method parameters.
    :raises ImportError: Missing backend; use install_skill_deps for paste-bio/POT
        or STalign/torch as appropriate.
    :raises RuntimeError: A slice cannot be aligned; partial success is not returned.
    """
    if method not in {"paste", "stalign"}:
        raise ValueError(f"Unknown registration method: {method}")
    slice_key = slice_key or detect_slice_key(adata)
    if slice_key is None or slice_key not in adata.obs:
        raise ValueError("A slice_key identifying at least two slices is required")
    if adata.obs[slice_key].isna().any() or adata.obs[slice_key].nunique() < 2:
        raise ValueError("At least two slices with nonmissing labels are required")
    if reference_slice is not None and str(reference_slice) not in set(adata.obs[slice_key].astype(str)):
        raise ValueError(f"Unknown reference_slice: {reference_slice}")
    if method == "stalign" and adata.obs[slice_key].nunique() != 2:
        raise ValueError("STalign requires exactly two slices")
    allowed = {"alpha", "dissimilarity", "use_gpu"} if method == "paste" else {"image_size", "niter", "a", "use_expression"}
    if parameters.keys() - allowed:
        raise ValueError(f"Unsupported {method} parameters: {sorted(parameters.keys() - allowed)}")
    if not 0 <= parameters.get("alpha", .1) <= 1:
        raise ValueError("alpha must be in [0, 1]")
    if parameters.get("dissimilarity", "kl") not in {"kl", "euclidean", "Euclidean"}:
        raise ValueError("dissimilarity must be kl or euclidean")
    for key in ("niter", "a"):
        if key in parameters and (not np.isfinite(parameters[key]) or parameters[key] <= 0):
            raise ValueError(f"{key} must be finite and positive")
    if "image_size" in parameters:
        size = parameters["image_size"]
        if isinstance(size, int):
            size = (size, size)
        if len(size) != 2 or any(int(v) != v or v < 2 for v in size):
            raise ValueError("image_size must contain two integers >= 2")
        parameters["image_size"] = tuple(size)
    try:
        summary = run_registration(adata, method=method, slice_key=slice_key,
                                   reference_slice=reference_slice, **parameters)
    except ImportError as exc:
        raise ImportError(f"Missing {method} backend; use install_skill_deps for spatial-register. {exc}") from exc
    adata.uns[_RUN_KEY] = json.dumps(summary)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the last registration summary.

    :param adata: Registered AnnData.
    :param keep: True retains diagnostics; False removes them for CLI serialization.
    :returns: Summary with reference, slices and effective parameters, or an empty dict.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def shift_table(adata) -> pd.DataFrame:
    """Measure Euclidean displacement from original to registered coordinates.

    :param adata: AnnData with spatial_aligned and original spatial coordinates.
    :returns: observation and shift_distance columns, in observation order.
    :raises KeyError: Aligned coordinates are absent.
    :raises ValueError: Original coordinates are absent.
    """
    key = require_spatial_coords(adata)
    shift = np.linalg.norm(adata.obsm["spatial_aligned"] - adata.obsm[key], axis=1)
    return pd.DataFrame({"observation": adata.obs_names.astype(str), "shift_distance": shift})


def registration_figure(adata, *, slice_key: str | None = None):
    """Plot original and registered slice coordinates side by side.

    :param adata: Registered AnnData.
    :param slice_key: Slice label column; None detects the column from the data.
    :returns: A matplotlib Figure; the caller saves and closes it.
    :raises KeyError: Aligned coordinates or labels are absent.
    """
    import matplotlib.pyplot as plt

    key = slice_key or detect_slice_key(adata)
    labels = adata.obs[key].astype(str)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, coords_key in zip(axes, (require_spatial_coords(adata), "spatial_aligned")):
        coords = adata.obsm[coords_key]
        for label in sorted(labels.unique()):
            mask = labels == label
            ax.scatter(coords[mask, 0], coords[mask, 1], label=label, s=8)
        ax.set(title=coords_key, aspect="equal", xlabel="x", ylabel="y")
        ax.invert_yaxis()
    axes[-1].legend(title=key)
    fig.tight_layout()
    return fig
