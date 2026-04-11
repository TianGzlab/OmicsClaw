#!/usr/bin/env python3
"""Single-Cell Doublet Detection with shared OmicsClaw scRNA contracts."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
import tempfile
from pathlib import Path

import h5py

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd
import scanpy as sc

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_output_readme,
    write_result_json,
)
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner
from skills.singlecell._lib import dependency_manager as sc_dep_manager
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import qc as sc_qc_utils
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    record_matrix_contract,
    select_count_like_expression_source,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import (
    _format_candidates,
    _obs_candidates,
    apply_preflight,
    preflight_sc_doublet_detection,
)
from skills.singlecell._lib.viz import (
    plot_doublet_call_summary,
    plot_doublet_score_by_group,
    plot_doublet_score_distribution,
    plot_embedding_categorical,
    plot_embedding_comparison,
    plot_embedding_continuous,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-doublet-detection"
SKILL_VERSION = "0.6.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py"

R_ENHANCED_PLOTS = {
    "plot_embedding_discrete": "r_embedding_discrete.png",
    "plot_embedding_feature": "r_embedding_feature.png",
    "plot_feature_violin": "r_feature_violin.png",
}

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "scrublet": MethodConfig(
        name="scrublet",
        description="Scrublet — Python-native first-pass doublet detection",
        dependencies=("scrublet",),
    ),
    "doubletdetection": MethodConfig(
        name="doubletdetection",
        description="DoubletDetection — consensus classifier borrowed from the SCOP method surface",
        dependencies=("doubletdetection",),
    ),
    "doubletfinder": MethodConfig(
        name="doubletfinder",
        description="DoubletFinder — R/Seurat-backed path",
        dependencies=(),
    ),
    "scdblfinder": MethodConfig(
        name="scdblfinder",
        description="scDblFinder — fast Bioconductor path",
        dependencies=(),
    ),
    "scds": MethodConfig(
        name="scds",
        description="scds — cxds/bcds/hybrid scores from Bioconductor",
        dependencies=(),
    ),
}


def _write_repro_requirements(repro_dir: Path, packages: list[str]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    lines: list[str] = []
    for pkg in packages:
        try:
            lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    (repro_dir / "requirements.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_standard_run_artifacts(output_dir: Path, result_payload: dict, summary: dict) -> None:
    notebook_path = None
    try:
        from omicsclaw.common.notebook_export import write_analysis_notebook

        notebook_path = write_analysis_notebook(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell doublet calling with standardized score and label outputs.",
            result_payload=result_payload,
            preferred_method=summary.get("executed_method", summary.get("method", "scrublet")),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell doublet detection with standardized score and label outputs.",
            result_payload=result_payload,
            preferred_method=summary.get("executed_method", summary.get("method", "scrublet")),
            notebook_path=notebook_path,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to write README.md: %s", exc)


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
):
    validate_r_environment(required_r_packages=required_packages)
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    export, source, _ = _build_count_like_export_adata(adata)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_doublet_r_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        export.write_h5ad(input_h5ad)
        with h5py.File(input_h5ad, "a") as handle:
            if "layers" in handle and len(handle["layers"].keys()) == 0:
                del handle["layers"]
        runner.run_script(
            script_name,
            args=[str(input_h5ad), str(output_dir), str(expected_doublet_rate), *(extra_args or [])],
            expected_outputs=[output_csv],
            output_dir=output_dir,
        )
        df = pd.read_csv(output_dir / output_csv, index_col=0)

    return df, source


def run_doubletfinder(adata, *, expected_doublet_rate: float):
    return _run_r_doublet_script(
        adata,
        script_name="sc_doubletfinder.R",
        output_csv="doubletfinder_results.csv",
        expected_doublet_rate=expected_doublet_rate,
        required_packages=["Seurat", "DoubletFinder", "SingleCellExperiment", "zellkonverter"],
    )


def run_scdblfinder(adata, *, expected_doublet_rate: float):
    return _run_r_doublet_script(
        adata,
        script_name="sc_scdblfinder.R",
        output_csv="scdblfinder_results.csv",
        expected_doublet_rate=expected_doublet_rate,
        required_packages=["scDblFinder", "SingleCellExperiment", "zellkonverter"],
    )


def _normalize_r_result(result, *, fallback_source: str = "unknown") -> tuple[pd.DataFrame, str]:
    """Accept either ``df`` or ``(df, source)`` from R-wrapper helpers."""
    if isinstance(result, tuple) and len(result) == 2:
        df, source = result
        return df, str(source)
    return result, fallback_source


def run_scds(adata, *, expected_doublet_rate: float, mode: str):
    return _run_r_doublet_script(
        adata,
        script_name="sc_scds.R",
        output_csv="scds_results.csv",
        expected_doublet_rate=expected_doublet_rate,
        required_packages=["scds", "SingleCellExperiment", "zellkonverter"],
        extra_args=[mode],
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
) -> dict:
    export, expression_source, _ = _build_count_like_export_adata(adata)
    export = sc_qc_utils.run_scrublet_detection(
        export,
        batch_key=batch_key,
        expected_doublet_rate=expected_doublet_rate,
        auto_rate=False,
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
) -> dict:
    doubletdetection = sc_dep_manager.require("doubletdetection", feature="doublet detection")
    export, expression_source, _ = _build_count_like_export_adata(adata)
    clf = doubletdetection.BoostClassifier(
        n_iters=n_iters,
        clustering_algorithm="leiden",
        standard_scaling=standard_scaling,
        random_state=0,
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


def detect_doublets_doubletfinder(adata, *, expected_doublet_rate: float) -> dict:
    try:
        df, expression_source = _normalize_r_result(
            run_doubletfinder(adata, expected_doublet_rate=expected_doublet_rate),
            fallback_source="unknown",
        )
        executed_method = "doubletfinder"
        fallback_reason = None
    except Exception as exc:
        logger.warning("DoubletFinder runtime failed (%s). Falling back to scDblFinder.", exc)
        df, expression_source = _normalize_r_result(
            run_scdblfinder(adata, expected_doublet_rate=expected_doublet_rate),
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


def detect_doublets_scdblfinder(adata, *, expected_doublet_rate: float) -> dict:
    df, expression_source = _normalize_r_result(
        run_scdblfinder(adata, expected_doublet_rate=expected_doublet_rate),
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


def detect_doublets_scds(adata, *, expected_doublet_rate: float, mode: str) -> dict:
    requested_mode = str(mode)
    executed_mode = requested_mode
    fallback_reason = None
    try:
        df, expression_source = _normalize_r_result(
            run_scds(adata, expected_doublet_rate=expected_doublet_rate, mode=requested_mode),
            fallback_source="unknown",
        )
    except Exception as exc:
        if requested_mode == "cxds":
            raise
        logger.warning("scds runtime failed for mode=%s (%s). Falling back to cxds.", requested_mode, exc)
        df, expression_source = _normalize_r_result(
            run_scds(adata, expected_doublet_rate=expected_doublet_rate, mode="cxds"),
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


def _candidate_embeddings(adata) -> list[str]:
    preferred = [key for key in ("X_umap", "X_tsne", "X_phate", "X_diffmap", "X_pca") if key in adata.obsm]
    if preferred:
        return preferred
    return [str(key) for key in adata.obsm.keys() if str(key).startswith("X_")]


def _resolve_compare_key(adata, batch_key: str | None) -> str | None:
    if batch_key and batch_key in adata.obs.columns:
        if adata.obs[batch_key].astype(str).nunique(dropna=False) > 1:
            return batch_key
        return None
    candidates = _obs_candidates(adata, "batch") or _obs_candidates(adata, "condition")
    for candidate in candidates:
        if candidate in adata.obs.columns and adata.obs[candidate].astype(str).nunique(dropna=False) > 1:
            return candidate
    return None


def _build_preview_embedding(adata):
    preview, _, _ = _build_count_like_export_adata(adata)
    for column in ("doublet_score", "predicted_doublet", "doublet_classification"):
        if column in adata.obs.columns:
            preview.obs[column] = adata.obs[column].values

    sc.pp.normalize_total(preview, target_sum=1e4)
    sc.pp.log1p(preview)
    if preview.n_vars > 2000:
        sc.pp.highly_variable_genes(preview, n_top_genes=min(2000, preview.n_vars), flavor="seurat")
        if "highly_variable" in preview.var.columns and int(preview.var["highly_variable"].sum()) >= 50:
            preview = preview[:, preview.var["highly_variable"]].copy()

    n_comps = min(30, max(2, preview.n_obs - 1), max(2, preview.n_vars - 1))
    sc.tl.pca(preview, n_comps=n_comps)
    sc.pp.neighbors(preview, n_neighbors=min(15, max(2, preview.n_obs - 1)), n_pcs=min(n_comps, preview.obsm["X_pca"].shape[1]))
    sc.tl.umap(preview)
    return preview, "X_umap", "Preview UMAP computed from raw counts for visualization only."


def _prepare_visualization_adata(adata):
    candidates = _candidate_embeddings(adata)
    if candidates:
        return adata, candidates[0], None
    try:
        return _build_preview_embedding(adata)
    except Exception as exc:
        logger.warning("Preview embedding computation failed: %s", exc)
        return adata, None, None


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


def _build_embedding_points_table(adata, embedding_key: str, extra_obs: list[str] | None = None) -> pd.DataFrame:
    coords = np.asarray(adata.obsm[embedding_key])
    if coords.shape[1] < 2:
        raise ValueError(f"{embedding_key} has fewer than 2 columns.")
    frame = pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "dim1": coords[:, 0],
            "dim2": coords[:, 1],
        }
    )
    for key in extra_obs or []:
        if key in adata.obs.columns:
            frame[key] = adata.obs[key].to_numpy()
    return frame


def _write_figure_data(output_dir: Path, *, calls_df: pd.DataFrame, summary_df: pd.DataFrame, group_df: pd.DataFrame, embedding_df: pd.DataFrame | None) -> dict[str, str]:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "doublet_calls": "doublet_calls.csv",
        "doublet_summary": "doublet_summary.csv",
    }
    calls_df.to_csv(figure_data_dir / files["doublet_calls"], index=False)
    summary_df.to_csv(figure_data_dir / files["doublet_summary"], index=False)
    if not group_df.empty:
        files["group_summary"] = "group_summary.csv"
        group_df.to_csv(figure_data_dir / files["group_summary"], index=False)
    if embedding_df is not None and not embedding_df.empty:
        files["embedding_points"] = "embedding_points.csv"
        embedding_df.to_csv(figure_data_dir / files["embedding_points"], index=False)
    (figure_data_dir / "manifest.json").write_text(
        json.dumps({"skill": SKILL_NAME, "available_files": files}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return files


def generate_figures(
    adata,
    output_dir: Path,
    *,
    summary: dict,
    params: dict,
    compare_key: str | None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    summary_df = _build_doublet_summary_table(summary)
    calls_df = _build_doublet_calls_table(adata, compare_key=compare_key)
    group_df = _build_group_summary_table(calls_df, compare_key)

    plot_doublet_score_distribution(
        adata.obs["doublet_score"],
        output_dir,
        threshold=params.get("threshold"),
        expected_rate=summary.get("expected_rate"),
    )
    plot_doublet_call_summary(summary_df, output_dir)

    viz_adata, embedding_key, preview_note = _prepare_visualization_adata(adata)
    embedding_df = None
    if embedding_key:
        plot_embedding_categorical(
            viz_adata,
            output_dir,
            obsm_key=embedding_key,
            color_key="doublet_classification",
            filename="embedding_doublet_calls.png",
            title="Doublet classification on embedding",
            subtitle=f"Embedding: {embedding_key}",
            legend=True,
            label_on_data=False,
        )
        plot_embedding_continuous(
            viz_adata,
            output_dir,
            obsm_key=embedding_key,
            color_key="doublet_score",
            filename="embedding_doublet_scores.png",
            title="Doublet score on embedding",
            subtitle=f"Embedding: {embedding_key}",
            cmap="mako",
        )
        if compare_key and compare_key in viz_adata.obs.columns and compare_key != "doublet_classification":
            plot_embedding_comparison(
                viz_adata,
                output_dir,
                obsm_key=embedding_key,
                color_keys=["doublet_classification", compare_key],
                filename="embedding_doublet_vs_group.png",
                title="Doublet calls versus grouping context",
            )
        embedding_df = _build_embedding_points_table(
            viz_adata,
            embedding_key,
            extra_obs=["doublet_classification", "doublet_score", compare_key] if compare_key else ["doublet_classification", "doublet_score"],
        )
    if compare_key:
        plot_doublet_score_by_group(calls_df, output_dir, group_key=compare_key)

    figure_data_files = _write_figure_data(
        output_dir,
        calls_df=calls_df,
        summary_df=summary_df,
        group_df=group_df,
        embedding_df=embedding_df,
    )
    return {
        "summary_df": summary_df,
        "calls_df": calls_df,
        "group_df": group_df,
        "embedding_df": embedding_df,
        "embedding_key": embedding_key,
        "preview_note": preview_note,
        "figure_data_files": figure_data_files,
    }


def _write_tables(output_dir: Path, gallery_context: dict[str, object]) -> None:
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    gallery_context["summary_df"].to_csv(tables_dir / "summary.csv", index=False)
    gallery_context["calls_df"].to_csv(tables_dir / "doublet_calls.csv", index=False)
    group_df = gallery_context["group_df"]
    if isinstance(group_df, pd.DataFrame) and not group_df.empty:
        group_df.to_csv(tables_dir / "group_summary.csv", index=False)


def write_report(output_dir: Path, summary: dict, params: dict, input_file: str | None, *, gallery_context: dict[str, object]) -> None:
    header = generate_report_header(
        title="Single-Cell Doublet Detection Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Requested method": str(summary["requested_method"]),
            "Executed method": str(summary["executed_method"]),
            "Doublets detected": str(summary["n_doublets"]),
            "Doublet rate": f"{summary['doublet_rate'] * 100:.2f}%",
        },
    )
    lines = [
        "## Summary\n",
        f"- **Requested method**: `{summary['requested_method']}`",
        f"- **Executed method**: `{summary['executed_method']}`",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Doublets detected**: {summary['n_doublets']}",
        f"- **Doublet rate**: {summary['doublet_rate'] * 100:.2f}%",
    ]
    if summary.get("expected_rate") is not None:
        lines.append(f"- **Expected doublet rate**: {summary['expected_rate'] * 100:.2f}%")
    if summary.get("fallback_reason"):
        lines.append(f"- **Fallback note**: {summary['fallback_reason']}")
    if summary.get("expression_source"):
        lines.append(f"- **Raw-count source used for calling**: `{summary['expression_source']}`")

    lines.extend(
        [
            "",
            "## First-pass Settings\n",
            f"- `method`: {params['method']}",
        ]
    )
    if "expected_doublet_rate" in params:
        lines.append(f"- `expected_doublet_rate`: {params.get('expected_doublet_rate')}")
    if params["method"] == "scrublet":
        lines.append(f"- `threshold`: {params.get('threshold') if params.get('threshold') is not None else 'auto'}")
        if params.get("batch_key"):
            lines.append(f"- `batch_key`: {params['batch_key']}")
    elif params["method"] == "doubletdetection":
        lines.append(f"- `doubletdetection_n_iters`: {params['doubletdetection_n_iters']}")
        lines.append(f"- `doubletdetection_standard_scaling`: {params['doubletdetection_standard_scaling']}")
    elif params["method"] == "scds":
        lines.append(f"- `scds_mode`: {params['scds_mode']}")
        if params.get("executed_scds_mode") and params["executed_scds_mode"] != params["scds_mode"]:
            lines.append(f"- `executed_scds_mode`: {params['executed_scds_mode']}")

    lines.extend(
        [
            "",
            "## Beginner Notes\n",
            "- Doublet detection usually belongs after QC review and before final clustering, annotation, or DE interpretation.",
            "- This skill **annotates** doublets; it does not silently remove cells.",
            "- If the calls look credible, keep singlets and rerun preprocessing / clustering as needed for the final downstream object.",
        ]
    )
    if gallery_context.get("preview_note"):
        lines.append(f"- {gallery_context['preview_note']}")

    lines.extend(
        [
            "",
            "## Recommended Next Steps\n",
            "- Inspect `figures/doublet_score_distribution.png` and `tables/doublet_calls.csv` first.",
            "- If many high-scoring cells cluster together, keep only singlets before final clustering or annotation.",
            "- After doublet review, common next steps are `sc-preprocessing`, `sc-clustering`, `sc-cell-annotation`, or `sc-de` depending on your stage.",
            "",
            "## Output Files\n",
            "- `processed.h5ad` — input AnnData plus standardized doublet score / label columns in `obs`.",
            "- `figures/` — doublet gallery (distribution, embedding calls, score map, optional group comparison).",
            "- `tables/doublet_calls.csv` — per-cell scores and calls for downstream filtering.",
            "- `figure_data/` — reusable figure-ready tables and coordinates.",
        ]
    )
    report = header + "\n".join(lines) + "\n" + generate_report_footer()
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def write_reproducibility(output_dir: Path, params: dict, input_file: str | None, *, demo_mode: bool = False) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file])
    else:
        command_parts.extend(["--input", "<input.h5ad>"])
    command_parts.extend(["--output", str(output_dir)])
    cli_keys = (
        "method",
        "expected_doublet_rate",
        "threshold",
        "batch_key",
        "doubletdetection_n_iters",
        "doubletdetection_standard_scaling",
        "scds_mode",
    )
    for key in cli_keys:
        value = params.get(key)
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if key == "doubletdetection_standard_scaling":
                command_parts.append(flag if value else "--no-doubletdetection-standard-scaling")
            continue
        if value not in (None, ""):
            command_parts.extend([flag, str(value)])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "scrublet", "doubletdetection"],
    )


def _ensure_output_contract(adata, *, source_path: str | None) -> tuple[dict, dict]:
    input_contract = ensure_input_contract(adata, source_path=source_path)
    existing = get_matrix_contract(adata)
    x_kind = existing.get("X") or infer_x_matrix_kind(adata)
    layers = dict(existing.get("layers") or {})

    try:
        matrix, _, _ = select_count_like_expression_source(adata, preferred_layer="counts")
        if "counts" not in adata.layers:
            adata.layers["counts"] = matrix.copy()
        if adata.raw is None:
            raw_snapshot = sc.AnnData(X=matrix.copy(), obs=adata.obs.copy(), var=adata.var.copy())
            raw_snapshot.obs_names = adata.obs_names.copy()
            raw_snapshot.var_names = adata.var_names.copy()
            adata.raw = raw_snapshot
        layers["counts"] = "raw_counts"
        raw_kind = "raw_counts_snapshot"
    except Exception:
        raw_kind = existing.get("raw")

    matrix_contract = record_matrix_contract(
        adata,
        x_kind=x_kind,
        raw_kind=raw_kind,
        layers=layers,
        producer_skill=SKILL_NAME,
        preprocess_method=existing.get("preprocess_method"),
        primary_cluster_key=existing.get("primary_cluster_key"),
    )
    return input_contract, matrix_contract


def _build_public_params(args, method: str, summary: dict) -> dict:
    params = {
        "method": method,
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
    }
    if method in {"scrublet", "doubletfinder", "scdblfinder", "scds"}:
        params["expected_doublet_rate"] = args.expected_doublet_rate
    if method == "scrublet":
        params["threshold"] = args.threshold
        if args.batch_key:
            params["batch_key"] = args.batch_key
    elif method == "doubletdetection":
        params["doubletdetection_n_iters"] = args.doubletdetection_n_iters
        params["doubletdetection_standard_scaling"] = bool(args.doubletdetection_standard_scaling)
    elif method == "scds":
        params["scds_mode"] = args.scds_mode
        params["executed_scds_mode"] = summary.get("executed_scds_mode", args.scds_mode)
    if summary.get("fallback_reason"):
        params["fallback_reason"] = summary["fallback_reason"]
    return params


def _dispatch_detection(adata, args, method: str) -> dict:
    if method == "scrublet":
        return detect_doublets_scrublet(
            adata,
            expected_doublet_rate=args.expected_doublet_rate,
            threshold=args.threshold,
            batch_key=args.batch_key,
        )
    if method == "doubletdetection":
        return detect_doublets_doubletdetection(
            adata,
            n_iters=args.doubletdetection_n_iters,
            standard_scaling=bool(args.doubletdetection_standard_scaling),
        )
    if method == "doubletfinder":
        return detect_doublets_doubletfinder(adata, expected_doublet_rate=args.expected_doublet_rate)
    if method == "scdblfinder":
        return detect_doublets_scdblfinder(adata, expected_doublet_rate=args.expected_doublet_rate)
    if method == "scds":
        return detect_doublets_scds(adata, expected_doublet_rate=args.expected_doublet_rate, mode=args.scds_mode)
    raise ValueError(f"Unsupported method: {method}")


def get_demo_data():
    adata, _ = sc_io.load_repo_demo_data("pbmc3k_raw")
    return adata


def _render_r_enhanced(output_dir, figure_data_dir, r_enhanced):
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Doublet Detection")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default="scrublet")
    parser.add_argument("--expected-doublet-rate", type=float, default=0.06)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--batch-key", default=None)
    parser.add_argument("--doubletdetection-n-iters", type=int, default=10)
    parser.add_argument(
        "--doubletdetection-standard-scaling",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--scds-mode", choices=["hybrid", "cxds", "bcds"], default="cxds")
    parser.add_argument("--r-enhanced", action="store_true", default=False, help="Generate R-enhanced figures via ggplot2 renderers")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc_io.smart_load(args.input_path, preserve_all=True, skill_name=SKILL_NAME)
        input_file = args.input_path

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback="scrublet")
    apply_preflight(
        preflight_sc_doublet_detection(
            adata,
            method=method,
            expected_doublet_rate=args.expected_doublet_rate,
            threshold=args.threshold,
            batch_key=args.batch_key,
            doubletdetection_n_iters=args.doubletdetection_n_iters,
            scds_mode=args.scds_mode,
            source_path=input_file,
        ),
        logger,
    )

    summary = _dispatch_detection(adata, args, method)
    summary.setdefault("requested_method", method)
    summary.setdefault("executed_method", summary.get("method", method))
    summary.setdefault("fallback_used", summary["requested_method"] != summary["executed_method"])
    summary["n_cells"] = int(adata.n_obs)

    compare_key = _resolve_compare_key(adata, args.batch_key)
    params = _build_public_params(args, method, summary)
    gallery_context = generate_figures(adata, output_dir, summary=summary, params=params, compare_key=compare_key)
    _write_tables(output_dir, gallery_context)
    write_report(output_dir, summary, params, input_file, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, input_file, demo_mode=args.demo)

    input_contract, matrix_contract = _ensure_output_contract(adata, source_path=input_file)
    store_analysis_metadata(adata, SKILL_NAME, summary["executed_method"], params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
        "fallback_used": bool(summary.get("fallback_used")),
        "fallback_reason": summary.get("fallback_reason"),
        "params": params,
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
        "visualization": {
            "embedding_key": gallery_context.get("embedding_key"),
            "preview_note": gallery_context.get("preview_note"),
            "available_figure_data": gallery_context.get("figure_data_files", {}),
        },
    }
    result_data["next_steps"] = [
        {"skill": "sc-filter", "reason": "Filter out detected doublets along with low-quality cells", "priority": "recommended"},
    ]
    r_enhanced_figures = _render_r_enhanced(output_dir, output_dir / "figure_data", args.r_enhanced)
    result_data["r_enhanced_figures"] = r_enhanced_figures
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"Doublet detection complete: {summary['n_doublets']} doublets "
        f"({summary['doublet_rate'] * 100:.1f}%), requested={summary['requested_method']}, "
        f"executed={summary['executed_method']}"
    )

    # --- Next-step guidance ---
    print()
    print("▶ Next step: Run sc-filter to remove flagged doublets")
    print(f"  python omicsclaw.py run sc-filter --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
