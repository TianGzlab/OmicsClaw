"""Ambient subtraction and SoupX correction on AnnData counts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

from skills._sdk import deps
from skills._sdk.r_script_runner import RScriptRunner
from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR
from skills.singlecell._lib.adata_utils import select_count_like_expression_source
from skills.singlecell._lib.r_exchange import write_matrix_exchange

__all__ = ["remove_ambient", "remove_ambient_soupx", "run_info", "correction_summary",
           "counts_comparison_table", "ambient_profile_table", "correction_figure"]
_RUN_KEY = "omicsclaw_sc_ambient_run"


def _remember(adata, *, method, contamination, expression_source, warnings):
    before = float(np.asarray(adata.layers["counts"].sum(axis=1)).mean())
    after = float(np.asarray(adata.X.sum(axis=1)).mean())
    adata.uns[_RUN_KEY] = json.dumps({
        "requested_method": method, "executed_method": method, "fallback_reason": None,
        "expression_source": expression_source, "warnings": warnings,
        "mean_before": before, "mean_after": after,
        "reduction_pct": float((1 - after / max(before, 1e-8)) * 100),
        "contamination_estimate": float(contamination), "method": method,
    })


def remove_ambient(adata, *, contamination: float = 0.05):
    """Subtract a mean ambient profile from count-like expression in place.

    Select layers['counts'], aligned raw or X; retain that matrix in
    layers['counts'] and replace X with nonnegative corrected values. The
    mean cell profile is only an approximation when empty droplets are absent.

    :param adata: AnnData with a count-like expression matrix.
    :param contamination: Fraction to subtract before clipping at zero, in [0, 1).
        Default 0.05, matching the CLI.
    :returns: The same AnnData; run_info reports the matrix source and reduction.
    :raises ValueError: No count-like matrix exists or contamination is invalid.
    """
    if not 0 <= contamination < 1:
        raise ValueError("contamination must be between 0 and 1, excluding 1")
    count_matrix, expression_source, warnings = select_count_like_expression_source(adata, preferred_layer="counts")
    ambient_profile = np.array(count_matrix.mean(axis=0)).flatten()
    ambient_profile = ambient_profile / max(ambient_profile.sum(), 1e-8)
    if sparse.issparse(count_matrix):
        csr = count_matrix.tocsr().astype(np.float32)
        n_cells, n_genes = csr.shape
        chunk_size = max(1, min(50_000, n_cells))
        corrected_chunks = []
        profile = ambient_profile.astype(np.float32)
        for start in range(0, n_cells, chunk_size):
            chunk = csr[start:start + chunk_size].toarray()
            cell_totals = chunk.sum(axis=1, keepdims=True)
            chunk -= contamination * cell_totals * profile[np.newaxis, :]
            np.maximum(chunk, 0, out=chunk)
            corrected_chunks.append(sparse.csr_matrix(chunk, dtype=np.float32))
        corrected = sparse.vstack(corrected_chunks, format="csr")
    else:
        corrected = np.asarray(count_matrix, dtype=np.float32).copy()
        cell_totals = corrected.sum(axis=1, keepdims=True)
        corrected = corrected - contamination * cell_totals * ambient_profile[np.newaxis, :]
        corrected = np.maximum(corrected, 0).astype(np.float32)
    adata.layers["counts"] = count_matrix.copy()
    adata.X = corrected
    adata.uns["ambient_correction"] = {
        "method": "simple", "contamination_fraction": contamination, "expression_source": expression_source,
    }
    _remember(adata, method="simple", contamination=contamination,
              expression_source=expression_source, warnings=warnings)
    return adata


def remove_ambient_soupx(adata, *, raw):
    """Return SoupX-corrected cells, using raw droplet counts to estimate ambient RNA.

    Both objects select counts from layers['counts'], aligned raw or X and
    exchange temporary 10x matrices with R. This backend does not expose a
    seed through its wrapper; results vary between runs. Errors propagate.

    :param adata: AnnData containing the filtered cells.
    :param raw: AnnData containing raw droplets, with matching feature names.
    :returns: A new AnnData aligned to SoupX's retained cells and genes, with
        original counts in layers['counts'] and corrected X.
    :raises RuntimeError: R, Seurat or SoupX is unavailable, or the method fails.
    :raises ValueError: Counts are missing or the result cannot be aligned.
    """
    deps.validate_r_environment(required_r_packages=["Seurat", "SoupX"])
    counts, source, warnings = select_count_like_expression_source(adata, preferred_layer="counts")
    raw_counts, _, _ = select_count_like_expression_source(raw, preferred_layer="counts")
    filtered = ad.AnnData(counts.copy(), obs=adata.obs.copy(), var=adata.var.copy())
    droplets = ad.AnnData(raw_counts.copy(), obs=raw.obs.copy(), var=raw.var.copy())
    runner = RScriptRunner(scripts_dir=_SDK_R_SCRIPTS_DIR, timeout=1800)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_soupx_") as temporary:
        folder = Path(temporary)
        raw_dir = write_matrix_exchange(droplets, folder / "raw", obs_columns=[], compressed=True)
        filtered_dir = write_matrix_exchange(filtered, folder / "filtered", obs_columns=[], compressed=True)
        output = folder / "output"
        output.mkdir()
        runner.run_script("sc_soupx.R", args=[str(raw_dir), str(filtered_dir), str(output)],
                          expected_outputs=["corrected_counts.csv", "cells.csv", "genes.csv", "contamination.json"],
                          output_dir=output)
        corrected = pd.read_csv(output / "corrected_counts.csv", index_col=0)
        cells = pd.read_csv(output / "cells.csv")["cell"].astype(str).tolist()
        genes = pd.read_csv(output / "genes.csv")["gene"].astype(str).tolist()
        contamination = json.loads((output / "contamination.json").read_text())["contamination"]
    common_cells = [str(cell) for cell in adata.obs_names if str(cell) in cells]
    common_genes = [str(gene) for gene in adata.var_names if str(gene) in genes]
    if not common_cells or not common_genes:
        raise ValueError("SoupX output could not be aligned to the input AnnData")
    result = adata[common_cells, common_genes].copy()
    result.layers["counts"] = filtered[common_cells, common_genes].X.copy()
    corrected.index = corrected.index.astype(str)
    corrected.columns = corrected.columns.astype(str)
    result.X = corrected.loc[common_genes, common_cells].T.to_numpy(dtype=np.float32)
    result.uns["soupx"] = {"contamination_fraction": float(contamination)}
    _remember(result, method="soupx", contamination=contamination,
              expression_source=source, warnings=warnings)
    return result


def run_info(adata, *, keep: bool = True) -> dict:
    """Read JSON correction diagnostics from adata.uns.

    :param adata: AnnData returned by a correction function.
    :param keep: False removes the diagnostics after reading; default True.
    :returns: Matrix source, method and before/after count summaries.
    """
    value = adata.uns.get(_RUN_KEY, "{}") if keep else adata.uns.pop(_RUN_KEY, "{}")
    return json.loads(value)


def correction_summary(adata) -> pd.DataFrame:
    """Return the recorded count reduction as a one-row table.

    :param adata: AnnData returned by a correction function.
    :returns: Mean counts, reduction_pct, contamination_estimate and method.
    """
    info = run_info(adata)
    return pd.DataFrame([{key: info[key] for key in
                          ("mean_before", "mean_after", "reduction_pct", "contamination_estimate", "method")}])


def counts_comparison_table(adata) -> pd.DataFrame:
    """Compare per-cell original counts in layers['counts'] with corrected X.

    :param adata: AnnData returned by a correction function.
    :returns: cell_id, counts_before and counts_after in observation order.
    """
    return pd.DataFrame({"cell_id": adata.obs_names.astype(str),
                         "counts_before": np.asarray(adata.layers["counts"].sum(axis=1)).ravel(),
                         "counts_after": np.asarray(adata.X.sum(axis=1)).ravel()})


def ambient_profile_table(adata) -> pd.DataFrame:
    """Return the mean original-count profile used by simple subtraction.

    :param adata: Corrected AnnData with original counts in layers['counts'].
    :returns: gene and fraction columns. This is not SoupX's estimated profile.
    """
    profile = np.asarray(adata.layers["counts"].mean(axis=0)).ravel()
    return pd.DataFrame({"gene": adata.var_names.astype(str), "fraction": profile / max(profile.sum(), 1e-8)})


def correction_figure(adata):
    """Plot original versus corrected counts per cell and return the Figure.

    :param adata: AnnData returned by a correction function.
    :returns: A matplotlib Figure for write_output.
    """
    from matplotlib import pyplot as plt
    frame = counts_comparison_table(adata)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(frame["counts_before"], frame["counts_after"], s=4, alpha=0.4)
    ax.set(xlabel="Original counts", ylabel="Corrected counts")
    fig.tight_layout()
    return fig
