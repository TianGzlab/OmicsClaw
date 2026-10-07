"""TF-target inference, optional motif pruning and explicit regulon scoring."""
from __future__ import annotations

import numpy as np
import pandas as pd
from skills.singlecell._lib import grn as methods

__all__ = ["infer_adjacencies", "run_info", "prune_regulons", "regulons_from_adjacencies",
           "score_regulons", "regulon_heatmap_figure"]


def infer_adjacencies(adata, *, tfs, method: str = "grnboost2", layer: str | None = None,
                      random_state: int = 42, n_top: int = 50, n_jobs: int = 4) -> pd.DataFrame:
    """Return TF, target and importance columns using the caller's TF list.

    grnboost2 retains the CLI's fallback to absolute Spearman correlation
    when its backend fails or returns no edges. Correlation excludes supplied
    TFs from candidate targets and keeps n_top targets per TF. No motif
    validation occurs here; run_info reports any fallback.

    :param tfs: TF names; only names present in the selected matrix are used.
    :param method: grnboost2 (default) or correlation.
    :param layer: Explicit expression layer; None prefers counts, aligned raw, then X.
    :param random_state: GRNBoost2 seed, default 42. Correlation is deterministic.
    :param n_top: Correlation targets per TF, default 50.
    :param n_jobs: GRNBoost2 workers, default 4.
    :returns: A new DataFrame; input AnnData is not modified.
    :raises ValueError: The method or budget is invalid, or no TF overlaps.
    """
    if method not in {"grnboost2", "correlation"} or min(n_top, n_jobs) < 1:
        raise ValueError("invalid inference method or target/worker budget")
    expression = methods.prepare_expression_matrix(adata, layer=layer)
    available = [str(tf) for tf in dict.fromkeys(tfs) if str(tf) in expression.columns]
    if not available:
        raise ValueError("None of the provided TFs are in the expression matrix")
    requested = method
    reason = None
    result = None
    if method == "grnboost2":
        try:
            result = methods.run_grnboost2(expression, available, seed=random_state, n_jobs=n_jobs)
        except ImportError:
            reason = "arboreto package not installed"
        except Exception as exc:
            reason = f"GRNBoost2 error: {exc}"
        if result is None or len(result) == 0:
            reason = reason or "GRNBoost2 returned empty results"
            method = "correlation"
    if method == "correlation":
        result = methods.run_correlation_grn(expression, available, method="spearman", n_top=n_top)
    result.attrs["run_info"] = {"requested_method": requested, "executed_method": method,
                                "fallback_used": reason is not None, "fallback_reason": reason,
                                "random_state": random_state, "tfs": available}
    return result


def run_info(adjacencies: pd.DataFrame) -> dict:
    """Return a copy of the inference backend and fallback record from DataFrame attrs."""
    return dict(adjacencies.attrs.get("run_info", {}))


def prune_regulons(adjacencies: pd.DataFrame, *, database_glob: str, motif_annotations: str,
                   n_top: int = 50, rank_threshold: int = 5000, auc_threshold: float = 0.05,
                   nes_threshold: float = 3.0, n_jobs: int = 4) -> list[dict]:
    """Return motif-pruned regulon dictionaries using the existing cisTarget bridge.

    Requires pySCENIC and caller-provided databases and motif annotations.
    Thresholds retain the CLI defaults: rank 5000, AUC 0.05, NES 3 and 50
    targets. Backend and resource errors propagate; no data are downloaded.
    """
    motifs, _ = methods.run_cistarget_pruning(adjacencies, database_glob=database_glob,
                                             motif_annotations_file=motif_annotations,
                                             rank_threshold=rank_threshold, auc_threshold=auc_threshold,
                                             nes_threshold=nes_threshold, n_jobs=n_jobs)
    return methods.derive_regulons(motifs, adjacencies, n_top_targets=n_top)


def regulons_from_adjacencies(adjacencies: pd.DataFrame, *, n_top: int = 50) -> list[dict]:
    """Group the strongest edges per TF without motif validation; default 50 targets."""
    if n_top < 1:
        raise ValueError("n_top must be positive")
    if adjacencies.empty:
        return []
    result = []
    for tf, group in adjacencies.groupby("TF", sort=False):
        selected = group.nlargest(n_top, "importance")
        result.append({"tf": tf, "targets": selected["target"].tolist(),
                       "n_targets": len(selected), "motif_nes": None})
    return result


def score_regulons(adata, regulons: list[dict], *, method: str = "aucell",
                   random_state: int = 42, n_jobs: int = 4) -> pd.DataFrame:
    """Return per-cell regulon scores without annotating the input.

    aucell requires pySCENIC and ranks count-layer/aligned-raw/X expression.
    mean averages each regulon's targets in X, matching the old simplified
    CLI. It is not AUCell, an enrichment statistic, or motif validation.

    :param method: aucell (default) or mean; no automatic scoring fallback.
    :param random_state: AUCell seed, default 42; mean is deterministic.
    :param n_jobs: AUCell workers, default 4.
    :returns: DataFrame indexed by cell; attrs names the scoring_method and is_aucell.
    :raises ValueError: The scoring method is unknown.
    :raises ImportError: AUCell's optional backend is unavailable.
    """
    if method == "aucell":
        result = methods.run_aucell_scoring(methods.prepare_expression_matrix(adata), regulons,
                                            seed=random_state, n_jobs=n_jobs)
    elif method == "mean":
        result = pd.DataFrame(index=adata.obs_names)
        for regulon in regulons:
            mask = adata.var_names.isin(regulon["targets"])
            if mask.any():
                values = adata.X[:, mask]
                values = values.toarray() if hasattr(values, "toarray") else values
                result[regulon["tf"]] = np.asarray(values).mean(axis=1)
    else:
        raise ValueError("score method must be aucell or mean")
    result.attrs.update(scoring_method=method, is_aucell=method == "aucell")
    return result


def regulon_heatmap_figure(scores: pd.DataFrame, *, groups: pd.Series | None = None):
    """Return a score heatmap, optionally averaged over aligned cell groups."""
    from matplotlib import pyplot as plt
    frame = scores if groups is None else scores.groupby(groups.reindex(scores.index), observed=False).mean()
    fig, ax = plt.subplots(figsize=(8, 5))
    plotted = ax.imshow(frame.T.to_numpy(), aspect="auto", interpolation="nearest")
    ax.set_yticks(range(len(frame.columns)), frame.columns)
    ax.set(xlabel="Groups" if groups is not None else "Cells", ylabel="Regulon")
    fig.colorbar(plotted, ax=ax, label=scores.attrs.get("scoring_method", "Score"))
    fig.tight_layout()
    return fig
