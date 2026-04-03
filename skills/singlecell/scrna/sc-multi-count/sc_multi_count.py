#!/usr/bin/env python3
"""Cell Ranger multi wrapper for mainstream multimodal 10x outputs."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd
from scipy import sparse

try:
    import anndata

    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_repro_requirements,
    write_result_json,
    write_standard_run_artifacts,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.multimodal import (
    available_multi_samples,
    build_barcode_summary,
    build_feature_type_summary,
    build_rna_handoff,
    detect_cellranger_multi_outs,
    inspect_cellranger_multi_run,
    load_multimodal_filtered_adata,
    run_cellranger_multi,
    split_feature_type_subsets,
    standardize_multimodal_adata,
)
from skills.singlecell._lib.viz import (
    plot_barcode_rank,
    plot_count_distributions,
    plot_feature_type_totals,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-multi-count"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-multi-count/sc_multi_count.py"


def _demo_multimodal():
    import scanpy as sc

    adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
    rna = adata.X.tocsr() if sparse.issparse(adata.X) else sparse.csr_matrix(adata.X)
    rng = np.random.default_rng(42)
    adt = sparse.csr_matrix(rng.poisson(1.2, size=(adata.n_obs, 12)))
    hto = sparse.csr_matrix(rng.poisson(0.6, size=(adata.n_obs, 4)))
    combined = sparse.hstack([rna, adt, hto], format="csr")

    multimodal = sc.AnnData(X=combined)
    multimodal.obs = adata.obs.copy()
    multimodal.obs_names = adata.obs_names.copy()
    multimodal.var_names = list(adata.var_names.astype(str)) + [f"ADT_{i+1}" for i in range(12)] + [f"HTO_{i+1}" for i in range(4)]
    multimodal.var["feature_types"] = (
        ["Gene Expression"] * adata.n_vars + ["Antibody Capture"] * 12 + ["Multiplexing Capture"] * 4
    )
    return multimodal, str(demo_path) if demo_path else None


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_tables(output_dir: Path, feature_summary: pd.DataFrame, barcode_summary: pd.DataFrame) -> dict[str, str]:
    tables_dir = output_dir / "tables"
    figure_data_dir = output_dir / "figure_data"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "feature_summary": "feature_type_summary.csv",
        "barcode_summary": "rna_barcode_metrics.csv",
    }
    feature_summary.to_csv(tables_dir / files["feature_summary"], index=False)
    barcode_summary.to_csv(tables_dir / files["barcode_summary"], index=False)
    feature_summary.to_csv(figure_data_dir / files["feature_summary"], index=False)
    barcode_summary.to_csv(figure_data_dir / files["barcode_summary"], index=False)
    _write_figure_data_manifest(
        output_dir,
        {
            "skill": SKILL_NAME,
            "available_files": {
                "feature_type_summary": files["feature_summary"],
                "rna_barcode_metrics": files["barcode_summary"],
            },
        },
    )
    return files


def _write_reproducibility(output_dir: Path, args: argparse.Namespace, *, demo_mode: bool) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif args.input_path:
        command_parts.extend(["--input", args.input_path])
    if args.sample:
        command_parts.extend(["--sample", args.sample])
    if args.threads != 8:
        command_parts.extend(["--threads", str(args.threads)])
    command_parts.extend(["--output", str(output_dir)])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    write_repro_requirements(output_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib"])


def _write_report(output_dir: Path, *, summary: dict, input_file: str | None, artifacts: dict[str, object], feature_summary: pd.DataFrame) -> None:
    header = generate_report_header(
        title="Single-Cell Multi Count Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file and Path(input_file).is_file() else None,
        extra_metadata={
            "Method": summary["method"],
            "Cells": str(summary["n_cells"]),
            "RNA genes": str(summary["n_rna_genes"]),
        },
    )
    lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cells in multimodal object**: {summary['n_cells']:,}",
        f"- **Total multimodal features**: {summary['n_features']:,}",
        f"- **RNA genes in handoff object**: {summary['n_rna_genes']:,}",
        f"- **Selected sample**: {summary['sample_id']}",
        "",
        "## Feature Types\n",
    ]
    for _, row in feature_summary.iterrows():
        lines.append(
            f"- **{row['feature_type']}**: {int(row['n_features'])} features, {row['total_counts']:.0f} total counts"
        )

    lines.extend(["", "## Preserved Artifacts\n"])
    for key, value in artifacts.items():
        lines.append(f"- **{key}**: {value}")

    lines.extend(
        [
            "",
            "## Output Files\n",
            "- `multimodal_standardized_input.h5ad` — preserved multimodal AnnData",
            "- `rna_standardized_input.h5ad` — RNA-only handoff for existing scRNA skills",
            "- `figures/feature_type_totals.png` — counts by feature type",
            "- `figures/rna_barcode_rank.png` — RNA barcode-rank curve",
            "- `figures/rna_count_distributions.png` — RNA barcode count distributions",
            "",
            "## Recommended Next Step\n",
            "- Current OmicsClaw downstream scRNA skills should use `rna_standardized_input.h5ad`.",
        ]
    )
    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + generate_report_footer(), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import or run Cell Ranger multi and export multimodal plus RNA-only handoff objects.")
    parser.add_argument("--input", dest="input_path", help="Cell Ranger multi config CSV or output directory")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run built-in demo mode")
    parser.add_argument("--sample", help="Choose one sample from per_sample_outs/")
    parser.add_argument("--threads", type=int, default=8, help="Thread count for real Cell Ranger multi runs")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_command: list[str] = []

    if args.demo:
        multimodal, input_file = _demo_multimodal()
        artifacts = {"source": "demo"}
        sample_id = "demo"
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input path not found: {input_path}")
        input_file = str(input_path)
        if input_path.suffix.lower() == ".csv" and not detect_cellranger_multi_outs(input_path):
            resolved, command = run_cellranger_multi(input_path, output_dir=output_dir, threads=args.threads)
            execution_command = list(command)
        else:
            resolved = inspect_cellranger_multi_run(input_path, sample=args.sample)

        if not args.sample and available_multi_samples(resolved.outs_dir):
            sample_id = "all_assigned_cells"
        else:
            sample_id = resolved.sample_id
        multimodal = load_multimodal_filtered_adata(resolved)
        artifacts = {
            "run_dir": str(resolved.run_dir),
            "outs_dir": str(resolved.outs_dir),
            "target_dir": str(resolved.target_dir),
            "filtered_h5": str(resolved.filtered_h5) if resolved.filtered_h5 else "",
            "qc_report_html": str(resolved.qc_report_html) if resolved.qc_report_html else "",
            "qc_library_metrics_csv": str(resolved.qc_library_metrics_csv) if resolved.qc_library_metrics_csv else "",
            "qc_sample_metrics_csv": str(resolved.qc_sample_metrics_csv) if resolved.qc_sample_metrics_csv else "",
        }

    multimodal_standardized, multimodal_contract = standardize_multimodal_adata(multimodal, skill_name=SKILL_NAME, method="cellranger_multi")
    rna_handoff, rna_contract = build_rna_handoff(multimodal_standardized, skill_name=SKILL_NAME, method="cellranger_multi")

    feature_summary = build_feature_type_summary(multimodal_standardized)
    barcode_summary = build_barcode_summary(rna_handoff)
    files = _export_tables(output_dir, feature_summary, barcode_summary)

    plot_feature_type_totals(feature_summary, output_dir)
    plot_barcode_rank(barcode_summary["total_counts"].to_numpy(), output_dir, filename="rna_barcode_rank.png")
    plot_count_distributions(rna_handoff, output_dir, filename="rna_count_distributions.png")
    _write_reproducibility(output_dir, args, demo_mode=args.demo)

    multimodal_path = output_dir / "multimodal_standardized_input.h5ad"
    rna_path = output_dir / "rna_standardized_input.h5ad"
    save_h5ad(multimodal_standardized, multimodal_path)
    save_h5ad(rna_handoff, rna_path)

    summary = {
        "method": "cellranger_multi",
        "sample_id": sample_id,
        "n_cells": int(multimodal_standardized.n_obs),
        "n_features": int(multimodal_standardized.n_vars),
        "n_rna_genes": int(rna_handoff.n_vars),
    }
    _write_report(output_dir, summary=summary, input_file=input_file, artifacts=artifacts, feature_summary=feature_summary)

    checksum = sha256_file(input_file) if input_file and Path(input_file).is_file() else ""
    result_data = {
        "method": "cellranger_multi",
        "params": {"sample": args.sample or "", "threads": int(args.threads)},
        "multimodal_input_contract": multimodal_contract,
        "rna_input_contract": rna_contract,
        "artifacts": artifacts,
        "visualization": {
            "available_figure_data": {
                "feature_type_summary": files["feature_summary"],
                "rna_barcode_metrics": files["barcode_summary"],
            }
        },
        "execution": execution_command,
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_standard_run_artifacts(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Import or run Cell Ranger multi and preserve multimodal plus RNA-only handoff AnnData objects.",
        result_payload=result_payload,
        preferred_method="cellranger_multi",
        script_path=Path(__file__).resolve(),
        actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
    )

    print(f"\n{'=' * 60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'=' * 60}")
    print(f"  Output directory: {output_dir}")
    print(f"  Multimodal cells: {summary['n_cells']:,}")
    print(f"  Multimodal features: {summary['n_features']:,}")
    print(f"  RNA handoff genes: {summary['n_rna_genes']:,}")


if __name__ == "__main__":
    main()
