"""Spatial proportions from a labelled reference AnnData."""
from __future__ import annotations

import numpy as np
import pandas as pd
from anndata import AnnData
from scipy import sparse
from skills.spatial._lib.deconvolution import METHOD_DISPATCH, COUNT_BASED_METHODS
from skills.spatial._lib.inference_result import store_info, read_info

__all__ = ["deconvolve", "run_info", "proportions", "proportions_figure"]
_RUN_KEY = "omicsclaw_spatial_deconv_run"


def _validate_expression(data, *, counts):
    matrix = data.X
    source = "X"
    if counts:
        if "counts" in data.layers:
            matrix = data.layers["counts"]
            source = "layers['counts']"
        elif data.raw is not None:
            matrix = data.raw.X
            source = "raw.X"
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Expression must be finite and nonnegative")
    if counts and not np.allclose(values, np.round(values)):
        raise ValueError("This method requires integer counts in layers['counts'], raw or X")
    return source


def deconvolve(adata, *, reference, method: str = "cell2location",
               cell_type_key: str = "cell_type", random_state: int = 0, **parameters):
    """Estimate proportions in place and return the same spatial AnnData.

    Count models read layers['counts'], raw or X in that order. FlashDeconv,
    Tangram and SPOTlight read nonnegative X. Reference data are copied.
    RCTD, SPOTlight and CARD retain their temporary R bridges; their wrappers
    do not expose a seed and results vary between runs.

    :param adata: Spatial AnnData; input expression is retained.
    :param reference: Required labelled reference AnnData; load it with read_input.
    :param method: CLI default cell2location; flashdeconv, rctd, destvi,
        stereoscope, tangram, spotlight and card are also supported.
    :param cell_type_key: Reference label column, CLI default cell_type.
    :param random_state: Seed for FlashDeconv/Tangram and scvi training, default 0.
    :param parameters: Method options in references/parameters.md, with CLI
        prefixes removed; omitted options keep their CLI defaults.
    :returns: The same AnnData with deconvolution_<method>, labels and JSON diagnostics.
    :raises ValueError: Invalid method, expression, reference labels or backend proportions.
    :raises TypeError: Reference is not AnnData or a method option is unknown.
    :raises ImportError: A backend is missing; use install_skill_deps for its named package.
    """
    if method not in METHOD_DISPATCH:
        raise ValueError(f"Unknown deconvolution method {method!r}")
    if not isinstance(reference, AnnData):
        raise TypeError("reference must be an AnnData loaded with read_input")
    if cell_type_key not in reference.obs or reference.obs[cell_type_key].isna().any():
        raise ValueError(f"Reference needs non-missing labels in {cell_type_key!r}")
    if not adata.obs_names.is_unique or not reference.obs_names.is_unique:
        raise ValueError("Observation identifiers must be unique")
    matrix_sources = {name: _validate_expression(data, counts=method in COUNT_BASED_METHODS)
                      for name, data in (("spatial", adata), ("reference", reference))}
    if "reference_path" in parameters:
        raise TypeError("Pass reference AnnData instead of reference_path")
    if method in {"flashdeconv", "tangram"}:
        parameters["random_state"] = random_state
    try:
        if method in {"cell2location", "destvi", "stereoscope"}:
            import scvi
            scvi.settings.seed = random_state
        table, summary = METHOD_DISPATCH[method](adata, reference_path=reference,
                                                cell_type_key=cell_type_key, **parameters)
    except ImportError as exc:
        raise ImportError(f"{exc}; use install_skill_deps for spatial-deconv") from exc
    table = table.copy()
    table.index = table.index.astype(str)
    table.columns = table.columns.astype(str)
    if not table.index.is_unique or not table.columns.is_unique or not adata.obs_names.isin(table.index).all():
        raise ValueError("Backend proportions must cover each spatial observation exactly once")
    table = table.loc[adata.obs_names]
    if not np.isfinite(table.to_numpy()).all() or (table.to_numpy() < 0).any():
        raise ValueError("Backend proportions must be finite and nonnegative")
    key = f"deconvolution_{method}"
    adata.obsm[key] = table.to_numpy()
    adata.uns[f"{key}_cell_types"] = list(table.columns)
    adata.uns[f"{key}_metadata"] = {"method": method, "cell_type_key": cell_type_key,
                                    "effective_params": summary.get("effective_params", {})}
    summary["cell_type_key"] = cell_type_key
    summary["random_state"] = None if method in {"rctd", "spotlight", "card"} else random_state
    summary["matrix_sources"] = matrix_sources
    store_info(adata, _RUN_KEY, summary)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read method settings, reference overlap and result diagnostics.

    :param adata: AnnData returned by deconvolve.
    :param keep: True retains diagnostics; False removes them before CLI serialization.
    :returns: Diagnostic dict with matrix_sources, seed (None for R wrappers)
        and optional CARD refinement tables.
    """
    return read_info(adata, _RUN_KEY, keep=keep)


def proportions(adata, *, method: str | None = None):
    """Return stored proportions with observation and cell-type identifiers.

    :param adata: AnnData returned by deconvolve; expression values are not read.
    :param method: None infers a sole stored method; specify it after multiple analyses.
    :returns: A DataFrame indexed by observation, with one column per reference label.
    :raises ValueError: No unique method can be inferred or label metadata are missing.
    """
    methods = [key.removeprefix("deconvolution_") for key in adata.obsm if key.startswith("deconvolution_")]
    if method is None:
        if len(methods) != 1:
            raise ValueError(f"Specify method; stored methods are {methods}")
        method = methods[0]
    key = f"deconvolution_{method}"
    labels = adata.uns.get(f"{key}_cell_types")
    if key not in adata.obsm or labels is None:
        raise ValueError(f"Missing stored matrix or cell-type labels for {method}")
    return pd.DataFrame(np.asarray(adata.obsm[key]).copy(), index=adata.obs_names, columns=list(labels))


def proportions_figure(adata, *, method: str | None = None):
    """Plot mean proportions per reference cell type.

    :param adata: AnnData returned by deconvolve; reads the stored proportion matrix.
    :param method: None infers a sole method; specify it for multiple results.
    :returns: A matplotlib Figure without writing files.
    :raises ValueError: No unique stored method is available.
    """
    import matplotlib.pyplot as plt
    means = proportions(adata, method=method).mean().sort_values(ascending=False)
    fig, ax = plt.subplots()
    ax.bar(means.index, means.to_numpy())
    ax.tick_params(axis="x", labelrotation=90)
    ax.set_ylabel("Mean proportion")
    fig.tight_layout()
    return fig
