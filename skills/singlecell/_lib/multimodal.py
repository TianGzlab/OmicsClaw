"""Helpers for multimodal 10x Cell Ranger multi outputs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse

from .adata_utils import record_standardized_input_contract, store_analysis_metadata
from .upstream import run_command, standardize_count_adata, tool_available

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CellRangerMultiArtifacts:
    """Resolved Cell Ranger multi artifact paths."""

    run_dir: Path
    outs_dir: Path
    target_dir: Path
    filtered_h5: Path | None
    filtered_matrix_dir: Path | None
    raw_h5: Path | None
    raw_matrix_dir: Path | None
    qc_report_html: Path | None
    qc_library_metrics_csv: Path | None
    qc_sample_metrics_csv: Path | None
    metrics_summary_csv: Path | None
    sample_id: str


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower() or "multi"


def detect_cellranger_multi_outs(path: str | Path) -> Path | None:
    """Return the `outs` directory for a Cell Ranger multi run when recognized."""
    candidate = Path(path)
    if (candidate / "outs").is_dir():
        candidate = candidate / "outs"
    if (candidate / "per_sample_outs").is_dir() or (candidate / "filtered_feature_bc_matrix.h5").exists():
        return candidate
    return None


def available_multi_samples(outs_dir: str | Path) -> list[str]:
    outs = Path(outs_dir)
    per_sample = outs / "per_sample_outs"
    if not per_sample.is_dir():
        return []
    return sorted(child.name for child in per_sample.iterdir() if child.is_dir())


def inspect_cellranger_multi_run(path: str | Path, sample: str | None = None) -> CellRangerMultiArtifacts:
    """Resolve stable artifact paths from a completed Cell Ranger multi run."""
    outs_dir = detect_cellranger_multi_outs(path)
    if outs_dir is None:
        raise FileNotFoundError(f"Could not locate Cell Ranger multi outputs under: {path}")

    run_dir = outs_dir.parent if outs_dir.name == "outs" else outs_dir
    per_sample_root = outs_dir / "per_sample_outs"
    sample_ids = available_multi_samples(outs_dir)
    if sample:
        if sample not in sample_ids:
            raise ValueError(f"Sample `{sample}` not found under per_sample_outs. Available: {', '.join(sample_ids) or 'none'}")
        target_dir = per_sample_root / sample
        filtered_h5 = target_dir / "sample_filtered_feature_bc_matrix.h5"
        filtered_matrix_dir = target_dir / "sample_filtered_feature_bc_matrix"
        raw_h5 = target_dir / "sample_raw_feature_bc_matrix.h5"
        raw_matrix_dir = target_dir / "sample_raw_feature_bc_matrix"
        metrics_summary_csv = target_dir / "metrics_summary.csv" if (target_dir / "metrics_summary.csv").exists() else None
        sample_id = sample
    else:
        target_dir = outs_dir
        filtered_h5 = outs_dir / "filtered_feature_bc_matrix.h5"
        filtered_matrix_dir = outs_dir / "filtered_feature_bc_matrix"
        raw_h5 = outs_dir / "raw_feature_bc_matrix.h5"
        raw_matrix_dir = outs_dir / "raw_feature_bc_matrix"
        metrics_summary_csv = None
        sample_id = "all_assigned_cells"

    return CellRangerMultiArtifacts(
        run_dir=run_dir,
        outs_dir=outs_dir,
        target_dir=target_dir,
        filtered_h5=filtered_h5 if filtered_h5.exists() else None,
        filtered_matrix_dir=filtered_matrix_dir if filtered_matrix_dir.is_dir() else None,
        raw_h5=raw_h5 if raw_h5.exists() else None,
        raw_matrix_dir=raw_matrix_dir if raw_matrix_dir.is_dir() else None,
        qc_report_html=outs_dir / "qc_report.html" if (outs_dir / "qc_report.html").exists() else None,
        qc_library_metrics_csv=outs_dir / "qc_library_metrics.csv" if (outs_dir / "qc_library_metrics.csv").exists() else None,
        qc_sample_metrics_csv=outs_dir / "qc_sample_metrics.csv" if (outs_dir / "qc_sample_metrics.csv").exists() else None,
        metrics_summary_csv=metrics_summary_csv,
        sample_id=sample_id,
    )


def run_cellranger_multi(
    config_csv: str | Path,
    *,
    output_dir: str | Path,
    threads: int = 8,
) -> tuple[CellRangerMultiArtifacts, tuple[str, ...]]:
    """Execute `cellranger multi` from a config CSV and return resolved artifacts."""
    if not tool_available("cellranger"):
        raise RuntimeError("`cellranger` is not installed or not on PATH.")

    config_path = Path(config_csv)
    if not config_path.exists():
        raise FileNotFoundError(f"Cell Ranger multi config CSV not found: {config_path}")

    run_root = Path(output_dir) / "artifacts" / "cellranger_multi"
    run_root.mkdir(parents=True, exist_ok=True)
    run_id = _slugify(config_path.stem)
    command = [
        "cellranger",
        "multi",
        f"--id={run_id}",
        f"--csv={config_path.resolve()}",
        f"--localcores={max(int(threads), 1)}",
    ]
    execution = run_command(command, cwd=run_root)
    return inspect_cellranger_multi_run(run_root / run_id), execution.command


def load_multimodal_filtered_adata(artifacts: CellRangerMultiArtifacts):
    """Load a filtered feature-barcode matrix from Cell Ranger multi outputs."""
    if artifacts.filtered_h5 and artifacts.filtered_h5.exists():
        return sc.read_10x_h5(artifacts.filtered_h5)
    if artifacts.filtered_matrix_dir and artifacts.filtered_matrix_dir.exists():
        try:
            return sc.read_10x_mtx(artifacts.filtered_matrix_dir, var_names="gene_symbols", cache=False)
        except Exception:
            return sc.read_10x_mtx(artifacts.filtered_matrix_dir, var_names="gene_ids", cache=False)
    raise FileNotFoundError(f"No filtered Cell Ranger multi matrix found under {artifacts.target_dir}")


def split_feature_type_subsets(adata) -> dict[str, object]:
    """Return modality-specific subsets keyed by feature type."""
    feature_types = (
        adata.var["feature_types"].astype(str)
        if "feature_types" in adata.var.columns else pd.Series(["Gene Expression"] * adata.n_vars, index=adata.var_names)
    )
    subsets: dict[str, object] = {}
    for feature_type in sorted(pd.unique(feature_types)):
        mask = feature_types.to_numpy() == feature_type
        if int(mask.sum()) == 0:
            continue
        subsets[str(feature_type)] = adata[:, mask].copy()
    return subsets


def build_feature_type_summary(adata) -> pd.DataFrame:
    """Summarize counts and feature counts per modality."""
    subsets = split_feature_type_subsets(adata)
    rows = []
    for feature_type, subset in subsets.items():
        rows.append(
            {
                "feature_type": feature_type,
                "n_features": int(subset.n_vars),
                "total_counts": float(np.asarray(subset.X.sum()).ravel()[0]),
                "n_cells": int(subset.n_obs),
            }
        )
    return pd.DataFrame(rows).sort_values("total_counts", ascending=False).reset_index(drop=True)


def build_barcode_summary(adata) -> pd.DataFrame:
    """Compute per-barcode metrics for an AnnData object."""
    matrix = adata.X
    return pd.DataFrame(
        {
            "barcode": adata.obs_names.astype(str),
            "total_counts": np.asarray(matrix.sum(axis=1)).ravel(),
            "detected_features": np.asarray((matrix > 0).sum(axis=1)).ravel(),
        }
    ).sort_values("total_counts", ascending=False).reset_index(drop=True)


def standardize_multimodal_adata(adata, *, skill_name: str, method: str):
    """Standardize a multimodal AnnData while preserving feature types."""
    standardized = adata.copy()
    standardized.obs_names = standardized.obs_names.astype(str)
    standardized.var_names = standardized.var_names.astype(str)
    standardized.obs_names_make_unique()
    standardized.var_names_make_unique()
    standardized.layers["counts"] = standardized.X.copy()
    contract = record_standardized_input_contract(
        standardized,
        expression_source=f"{method}.multimodal_matrix",
        gene_name_source="var_names",
        warnings=[],
        standardizer_skill=skill_name,
    )
    store_analysis_metadata(standardized, skill_name, method, {"multimodal": True})
    return standardized, contract


def build_rna_handoff(adata, *, skill_name: str, method: str):
    """Create the RNA-only downstream handoff from a multimodal object."""
    subsets = split_feature_type_subsets(adata)
    rna = subsets.get("Gene Expression")
    if rna is None:
        rna = subsets.get("Gene")
    if rna is None:
        raise ValueError("No `Gene Expression` feature type was found in the multimodal matrix.")
    return standardize_count_adata(
        rna,
        skill_name=skill_name,
        method=method,
        source_label=f"{method}.rna_subset",
        warnings=[],
    )
