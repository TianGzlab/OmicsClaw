"""Doublet scores, calls and summaries without removing observations."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import anndata as sc
import numpy as np
import pandas as pd

from skills._sdk import deps as sc_dep_manager
from skills._sdk.deps import validate_r_environment
from skills._sdk.r_script_runner import RScriptRunner
from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR
from skills.singlecell._lib import qc as sc_qc_utils
from skills.singlecell._lib.adata_utils import select_count_like_expression_source
from skills.singlecell._lib.r_exchange import write_matrix_exchange

__all__ = ["detect_doublets", "run_info", "doublet_calls_table", "doublet_summary",
           "group_summary_table", "doublet_score_figure"]
_RUN_KEY = "omicsclaw_sc_doublet_run"
logger = logging.getLogger(__name__)


def detect_doublets(adata, *, method: str = "scrublet", expected_doublet_rate: float = 0.06,
                    threshold: float | None = None, batch_key: str | None = None,
                    n_iters: int = 10, standard_scaling: bool = False,
                    scds_mode: str = "cxds", random_state: int = 0):
    """Annotate doublets in place using counts from layers['counts'], raw or X.

    No observations or features are removed. Pass the result to sc-filter
    when doublets should be removed. A DoubletFinder failure may fall back to
    scDblFinder; a failed scds mode may fall back to cxds. run_info records both.

    :param adata: AnnData containing a count-like matrix.
    :param method: scrublet, doubletdetection, doubletfinder, scdblfinder or scds.
    :param expected_doublet_rate: Expected doublet fraction; default 0.06.
    :param threshold: Scrublet score cutoff; None keeps its automatic calls.
    :param batch_key: Scrublet batches in obs; None analyzes all cells together.
    :param n_iters: DoubletDetection iterations; default 10.
    :param standard_scaling: DoubletDetection standard scaling; default False.
    :param scds_mode: cxds, bcds or hybrid; default cxds.
    :param random_state: Seed passed to the selected backend; default 0.
    :returns: The same AnnData with doublet_score, predicted_doublet and
        doublet_classification in obs, plus JSON diagnostics in uns.
    :raises ValueError: A method, rate, threshold or batch column is invalid.
    :raises ImportError: A Python backend is missing; use install_skill_deps.
    :raises RuntimeError: An R method and any documented fallback fail.
    """
    if not 0 < expected_doublet_rate < 1:
        raise ValueError("expected_doublet_rate must be between 0 and 1")
    if batch_key is not None and batch_key not in adata.obs:
        raise ValueError(f"batch column {batch_key!r} is missing")
    if threshold is not None and (method != "scrublet" or not 0 <= threshold <= 1):
        raise ValueError("threshold is a Scrublet score cutoff between 0 and 1")
    if n_iters < 1 or scds_mode not in {"cxds", "bcds", "hybrid"}:
        raise ValueError("n_iters must be positive and scds_mode must be cxds, bcds or hybrid")
    if method == "scrublet":
        info = detect_doublets_scrublet(adata, expected_doublet_rate=expected_doublet_rate,
                                       threshold=threshold, batch_key=batch_key, random_state=random_state)
    elif method == "doubletdetection":
        info = detect_doublets_doubletdetection(adata, n_iters=n_iters, standard_scaling=standard_scaling,
                                               random_state=random_state)
    elif method == "doubletfinder":
        info = detect_doublets_doubletfinder(adata, expected_doublet_rate=expected_doublet_rate, random_state=random_state)
    elif method == "scdblfinder":
        info = detect_doublets_scdblfinder(adata, expected_doublet_rate=expected_doublet_rate, random_state=random_state)
    elif method == "scds":
        info = detect_doublets_scds(adata, expected_doublet_rate=expected_doublet_rate, mode=scds_mode,
                                  random_state=random_state)
    else:
        raise ValueError(f"Unsupported method: {method}")
    info["n_cells"] = int(adata.n_obs)
    adata.uns[_RUN_KEY] = json.dumps(info)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read doublet method diagnostics from adata.uns.

    :param adata: AnnData annotated by detect_doublets.
    :param keep: False removes the JSON diagnostics after reading; default True.
    :returns: Method, counts, matrix source and any fallback details.
    """
    value = adata.uns.get(_RUN_KEY, "{}") if keep else adata.uns.pop(_RUN_KEY, "{}")
    return json.loads(value)


def doublet_calls_table(adata, *, groupby: str | None = None) -> pd.DataFrame:
    """Return per-cell scores and calls in observation order.

    :param adata: AnnData annotated by detect_doublets.
    :param groupby: Optional obs column to include in the table.
    :returns: A DataFrame with cell_id, scores, calls and classification.
    """
    return _build_doublet_calls_table(adata, compare_key=groupby)


def doublet_summary(adata) -> pd.DataFrame:
    """Return singlet and doublet counts and percentages from obs calls.

    :param adata: AnnData with predicted_doublet in obs.
    :returns: A DataFrame with one row per classification.
    """
    return _build_doublet_summary_table({"n_cells": adata.n_obs,
                                        "n_doublets": int(adata.obs["predicted_doublet"].sum())})


def group_summary_table(adata, *, groupby: str) -> pd.DataFrame:
    """Summarize doublet counts and scores for an obs grouping column.

    :param adata: AnnData annotated by detect_doublets.
    :param groupby: Existing obs column defining the groups.
    :returns: A DataFrame with counts, median and mean scores, and rates.
    :raises ValueError: The grouping column is missing.
    """
    if groupby not in adata.obs:
        raise ValueError(f"group column {groupby!r} is missing")
    return _build_group_summary_table(doublet_calls_table(adata, groupby=groupby), groupby)


def doublet_score_figure(adata):
    """Plot the doublet score distribution and return the Figure.

    :param adata: AnnData with doublet_score in obs.
    :returns: A matplotlib Figure; the caller saves it with write_output.
    """
    from matplotlib import pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(adata.obs["doublet_score"].dropna(), bins=40)
    ax.set(xlabel="Doublet score", ylabel="Cells")
    fig.tight_layout()
    return fig


def _build_count_like_export_adata(adata):
    matrix, source, warnings = select_count_like_expression_source(adata, preferred_layer="counts")
    export = sc.AnnData(X=matrix.copy(), obs=adata.obs.copy(), var=adata.var.copy())
    export.obs_names = adata.obs_names.copy()
    export.var_names = adata.var_names.copy()
    return export, source, warnings



def _run_r_doublet_script(
    adata,
    *,
    script_name: str,
    output_csv: str,
    required_packages: list[str],
    expected_doublet_rate: float,
    extra_args: list[str] | None = None,
    random_state: int = 0,
):
    validate_r_environment(required_r_packages=required_packages)
    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    export, source, _ = _build_count_like_export_adata(adata)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_doublet_r_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_dir = write_matrix_exchange(export, tmpdir / "input", obs_columns=[])
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        runner.run_script(
            script_name,
            args=[str(input_dir), str(output_dir), str(expected_doublet_rate), *(extra_args or []), str(random_state)],
            expected_outputs=[output_csv],
            output_dir=output_dir,
        )
        df = pd.read_csv(output_dir / output_csv, index_col=0)

    return df, source



def run_doubletfinder(adata, *, expected_doublet_rate: float, random_state: int = 0):
    return _run_r_doublet_script(
        adata,
        script_name="sc_doubletfinder.R",
        output_csv="doubletfinder_results.csv",
        expected_doublet_rate=expected_doublet_rate,
        required_packages=["Seurat", "DoubletFinder", "Matrix"],
        random_state=random_state,
    )



def run_scdblfinder(adata, *, expected_doublet_rate: float, random_state: int = 0):
    return _run_r_doublet_script(
        adata,
        script_name="sc_scdblfinder.R",
        output_csv="scdblfinder_results.csv",
        expected_doublet_rate=expected_doublet_rate,
        required_packages=["scDblFinder", "SingleCellExperiment", "Matrix"],
        random_state=random_state,
    )



def _normalize_r_result(result, *, fallback_source: str = "unknown") -> tuple[pd.DataFrame, str]:
    """Accept either ``df`` or ``(df, source)`` from R-wrapper helpers."""
    if isinstance(result, tuple) and len(result) == 2:
        df, source = result
        return df, str(source)
    return result, fallback_source



def run_scds(adata, *, expected_doublet_rate: float, mode: str, random_state: int = 0):
    return _run_r_doublet_script(
        adata,
        script_name="sc_scds.R",
        output_csv="scds_results.csv",
        expected_doublet_rate=expected_doublet_rate,
        required_packages=["scds", "SingleCellExperiment", "Matrix"],
        extra_args=[mode],
        random_state=random_state,
    )



def _copy_doublet_columns(source_adata, target_adata) -> None:
    for key in ("doublet_score", "predicted_doublet", "doublet_classification"):
        if key in source_adata.obs.columns:
            target_adata.obs[key] = source_adata.obs[key].values



def detect_doublets_scrublet(
    adata,
    *,
    expected_doublet_rate: float,
    threshold: float | None,
    batch_key: str | None,
    random_state: int = 0,
) -> dict:
    export, expression_source, _ = _build_count_like_export_adata(adata)
    export = sc_qc_utils.run_scrublet_detection(
        export,
        batch_key=batch_key,
        expected_doublet_rate=expected_doublet_rate,
        auto_rate=False,
        random_state=random_state,
    )
    export.obs["doublet_classification"] = np.where(export.obs["predicted_doublet"], "Doublet", "Singlet")
    if threshold is not None:
        export.obs["predicted_doublet"] = export.obs["doublet_score"] > threshold
        export.obs["doublet_classification"] = np.where(export.obs["predicted_doublet"], "Doublet", "Singlet")

    _copy_doublet_columns(export, adata)
    n_doublets = int(adata.obs["predicted_doublet"].sum())
    return {
        "method": "scrublet",
        "requested_method": "scrublet",
        "executed_method": "scrublet",
        "fallback_used": False,
        "fallback_reason": None,
        "n_doublets": n_doublets,
        "doublet_rate": float(n_doublets / max(adata.n_obs, 1)),
        "expected_rate": expected_doublet_rate,
        "expression_source": expression_source,
        "batch_key": batch_key,
    }



def detect_doublets_doubletdetection(
    adata,
    *,
    n_iters: int,
    standard_scaling: bool,
    random_state: int = 0,
) -> dict:
    doubletdetection = sc_dep_manager.require("doubletdetection", feature="doublet detection")
    export, expression_source, _ = _build_count_like_export_adata(adata)
    clf = doubletdetection.BoostClassifier(
        n_iters=n_iters,
        clustering_algorithm="leiden",
        standard_scaling=standard_scaling,
        random_state=random_state,
        verbose=False,
        n_jobs=1,
    )
    clf_fit = clf.fit(export.X)
    scores = np.asarray(clf_fit.doublet_score()).ravel()
    labels = np.asarray(clf_fit.predict()).ravel()
    predicted = labels.astype(int) != 0

    adata.obs["doublet_score"] = scores
    adata.obs["predicted_doublet"] = predicted
    adata.obs["doublet_classification"] = np.where(predicted, "Doublet", "Singlet")
    n_doublets = int(predicted.sum())
    return {
        "method": "doubletdetection",
        "requested_method": "doubletdetection",
        "executed_method": "doubletdetection",
        "fallback_used": False,
        "fallback_reason": None,
        "n_doublets": n_doublets,
        "doublet_rate": float(n_doublets / max(adata.n_obs, 1)),
        "expression_source": expression_source,
    }



def _apply_r_results(adata, df: pd.DataFrame) -> None:
    df = df.reindex(adata.obs_names)
    adata.obs["doublet_score"] = pd.to_numeric(df["doublet_score"], errors="coerce").values
    classification = df["classification"].fillna("Singlet").astype(str).str.strip()
    adata.obs["doublet_classification"] = classification.str.capitalize().values
    adata.obs["predicted_doublet"] = df["predicted_doublet"].fillna(False).astype(bool).values



def detect_doublets_doubletfinder(adata, *, expected_doublet_rate: float, random_state: int = 0) -> dict:
    try:
        df, expression_source = _normalize_r_result(
            run_doubletfinder(adata, expected_doublet_rate=expected_doublet_rate, random_state=random_state),
            fallback_source="unknown",
        )
        executed_method = "doubletfinder"
        fallback_reason = None
    except Exception as exc:
        logger.warning("DoubletFinder runtime failed (%s). Falling back to scDblFinder.", exc)
        df, expression_source = _normalize_r_result(
            run_scdblfinder(adata, expected_doublet_rate=expected_doublet_rate, random_state=random_state),
            fallback_source="unknown",
        )
        executed_method = "scdblfinder"
        fallback_reason = f"DoubletFinder runtime failed and wrapper fell back to scDblFinder: {exc}"

    _apply_r_results(adata, df)
    n_doublets = int(adata.obs["predicted_doublet"].sum())
    return {
        "method": executed_method,
        "requested_method": "doubletfinder",
        "executed_method": executed_method,
        "fallback_used": fallback_reason is not None,
        "fallback_reason": fallback_reason,
        "n_doublets": n_doublets,
        "doublet_rate": float(n_doublets / max(adata.n_obs, 1)),
        "expected_rate": expected_doublet_rate,
        "expression_source": expression_source,
    }



def detect_doublets_scdblfinder(adata, *, expected_doublet_rate: float, random_state: int = 0) -> dict:
    df, expression_source = _normalize_r_result(
        run_scdblfinder(adata, expected_doublet_rate=expected_doublet_rate, random_state=random_state),
        fallback_source="unknown",
    )
    _apply_r_results(adata, df)
    n_doublets = int(adata.obs["predicted_doublet"].sum())
    return {
        "method": "scdblfinder",
        "requested_method": "scdblfinder",
        "executed_method": "scdblfinder",
        "fallback_used": False,
        "fallback_reason": None,
        "n_doublets": n_doublets,
        "doublet_rate": float(n_doublets / max(adata.n_obs, 1)),
        "expected_rate": expected_doublet_rate,
        "expression_source": expression_source,
    }



def detect_doublets_scds(adata, *, expected_doublet_rate: float, mode: str, random_state: int = 0) -> dict:
    requested_mode = str(mode)
    executed_mode = requested_mode
    fallback_reason = None
    try:
        df, expression_source = _normalize_r_result(
            run_scds(adata, expected_doublet_rate=expected_doublet_rate, mode=requested_mode, random_state=random_state),
            fallback_source="unknown",
        )
    except Exception as exc:
        if requested_mode == "cxds":
            raise
        logger.warning("scds runtime failed for mode=%s (%s). Falling back to cxds.", requested_mode, exc)
        df, expression_source = _normalize_r_result(
            run_scds(adata, expected_doublet_rate=expected_doublet_rate, mode="cxds", random_state=random_state),
            fallback_source="unknown",
        )
        executed_mode = "cxds"
        fallback_reason = f"scds mode `{requested_mode}` failed and wrapper fell back to `cxds`: {exc}"
    _apply_r_results(adata, df)
    n_doublets = int(adata.obs["predicted_doublet"].sum())
    return {
        "method": "scds",
        "requested_method": "scds",
        "executed_method": "scds",
        "fallback_used": fallback_reason is not None,
        "fallback_reason": fallback_reason,
        "n_doublets": n_doublets,
        "doublet_rate": float(n_doublets / max(adata.n_obs, 1)),
        "expected_rate": expected_doublet_rate,
        "expression_source": expression_source,
        "requested_scds_mode": requested_mode,
        "executed_scds_mode": executed_mode,
    }



def _build_doublet_summary_table(summary: dict) -> pd.DataFrame:
    n_cells = max(int(summary["n_cells"]), 1)
    n_doublets = int(summary["n_doublets"])
    n_singlets = int(n_cells - n_doublets)
    frame = pd.DataFrame(
        [
            {"classification": "Singlet", "n_cells": n_singlets, "proportion_pct": 100.0 * n_singlets / n_cells},
            {"classification": "Doublet", "n_cells": n_doublets, "proportion_pct": 100.0 * n_doublets / n_cells},
        ]
    )
    return frame



def _build_doublet_calls_table(adata, compare_key: str | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "doublet_score": pd.to_numeric(adata.obs["doublet_score"], errors="coerce").to_numpy(),
            "predicted_doublet": adata.obs["predicted_doublet"].astype(bool).to_numpy(),
            "doublet_classification": adata.obs["doublet_classification"].astype(str).to_numpy(),
        }
    )
    if compare_key and compare_key in adata.obs.columns:
        frame[compare_key] = adata.obs[compare_key].astype(str).to_numpy()
    return frame



def _build_group_summary_table(calls_df: pd.DataFrame, compare_key: str | None) -> pd.DataFrame:
    if not compare_key or compare_key not in calls_df.columns:
        return pd.DataFrame()
    grouped = (
        calls_df.groupby(compare_key, dropna=False)
        .agg(
            n_cells=("cell_id", "count"),
            n_doublets=("predicted_doublet", "sum"),
            median_score=("doublet_score", "median"),
            mean_score=("doublet_score", "mean"),
        )
        .reset_index()
    )
    grouped["doublet_rate_pct"] = 100.0 * grouped["n_doublets"] / grouped["n_cells"].clip(lower=1)
    return grouped
