"""Copy-number inference from spatial expression and gene positions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from skills.spatial._lib.cnv import run_cnv
from skills.spatial._lib.inference_result import read_info, store_info

__all__ = ["cnv", "run_info", "scores", "cnv_figure"]
_RUN_KEY = "omicsclaw_spatial_cnv_run"


def cnv(adata, *, method: str = "infercnvpy", reference_key: str | None = None,
        reference_cat: list[str] | str | None = None, window_size: int = 100,
        step: int = 10, method_params: dict | None = None, random_state: int = 0,
        allele_counts: pd.DataFrame | None = None):
    """Infer CNV in place from log-normalized X or Numbat raw counts.

    infercnvpy needs var chromosome/start/end. Numbat needs layers['counts'],
    phased allele_counts and a diploid reference annotation. Counts and metadata
    are exchanged with R inside a temporary directory.

    :param adata: AnnData with expression and method-specific annotations.
    :param method: infercnvpy (CLI default) or numbat.
    :param reference_key: Observation column marking reference cells; None uses all cells.
    :param reference_cat: Reference labels; None uses the backend's global reference.
    :param window_size: Genomic smoothing window, 100 genes by default.
    :param step: Sliding-window stride, 10 genes by default.
    :param method_params: CLI options with underscores, such as infercnv_n_jobs=1;
        None keeps defaults listed in references/parameters.md.
    :param random_state: infercnvpy PCA/graph/clustering and Numbat R seed, default 0.
    :param allele_counts: Numbat long-form DataFrame with cell/snp_id/CHROM/POS/AD/DP/GT/gene;
        None reads the legacy obsm['allele_counts'] table. Multiple SNPs per cell are allowed.
    :returns: The same AnnData with CNV matrices, scores and JSON diagnostics.
    :raises ValueError: Missing genomic annotations, raw counts or invalid parameters.
    :raises ImportError: Missing infercnvpy or R backend; use install_skill_deps.
    """
    if window_size < 5 or not 1 <= step <= window_size:
        raise ValueError("window_size must be >= 5 and step in [1, window_size]")
    if reference_cat and not reference_key:
        raise ValueError("reference_cat requires reference_key")
    if method == "infercnvpy" and not {"chromosome", "start", "end"} <= set(adata.var):
        raise ValueError("infercnvpy requires genomic chromosome/start/end annotations")
    if method == "numbat":
        if "counts" not in adata.layers:
            raise ValueError("Numbat requires raw integer layers['counts']")
        counts = adata.layers["counts"]
        values = counts.data if hasattr(counts, "tocsr") else np.asarray(counts)
        if not np.isfinite(values).all() or (values < 0).any() or not np.equal(values, np.round(values)).all():
            raise ValueError("Numbat counts must be finite nonnegative integers")
        if allele_counts is None and "allele_counts" not in adata.obsm:
            raise ValueError("Numbat requires phased allele_counts")
    options = dict(method_params or {})
    options.setdefault("infercnv_exclude_chromosomes", ["chrX", "chrY"])
    try:
        summary = run_cnv(adata, method=method, reference_key=reference_key,
                          reference_cat=reference_cat, window_size=window_size,
                          step=step, random_state=random_state,
                          numbat_allele_counts=allele_counts, **options)
    except ImportError as exc:
        raise ImportError(f"{method} backend unavailable: {exc}; use install_skill_deps") from exc
    summary["random_state"] = random_state
    store_info(adata, _RUN_KEY, summary)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the last CNV inference diagnostics.

    :param adata: AnnData returned by cnv.
    :param keep: True retains diagnostics; False removes them before CLI serialization.
    :returns: Method, score summary, seed and any fallback details, or an empty dict.
    """
    return read_info(adata, _RUN_KEY, keep=keep)


def scores(adata) -> pd.DataFrame:
    """Return CNV scores and labels in observation order.

    :param adata: AnnData after CNV inference.
    :returns: Barcode-indexed table of available CNV score/label/uncertainty columns.
    """
    names = [key for key in ("cnv_score", "cnv_leiden", "numbat_p_cnv", "numbat_clone", "numbat_entropy") if key in adata.obs]
    return adata.obs[names].copy()


def cnv_figure(adata, *, basis: str = "spatial"):
    """Plot CNV scores over supplied coordinates without saving.

    :param adata: AnnData after CNV inference.
    :param basis: Coordinate key, spatial by default; X_umap is also supported.
    :returns: A matplotlib Figure owned by the caller.
    :raises KeyError: Missing coordinates or CNV score.
    """
    import matplotlib.pyplot as plt

    key = "cnv_score" if "cnv_score" in adata.obs else "numbat_p_cnv"
    coords = np.asarray(adata.obsm[basis])
    fig, ax = plt.subplots(figsize=(6, 5))
    points = ax.scatter(coords[:, 0], coords[:, 1], c=adata.obs[key], s=16)
    fig.colorbar(points, ax=ax, label=key)
    fig.tight_layout()
    return fig
