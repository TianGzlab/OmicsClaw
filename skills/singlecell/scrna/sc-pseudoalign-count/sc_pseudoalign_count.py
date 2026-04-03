#!/usr/bin/env python3
"""Pseudoalignment count wrapper for simpleaf and kb-python."""

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
from skills.singlecell._lib.pseudoalign import (
    inspect_pseudoalign_output,
    load_pseudoalign_adata,
    run_kb_count,
    run_simpleaf_quant,
)
from skills.singlecell._lib.upstream import (
    choose_fastq_sample,
    discover_fastq_samples,
    standardize_count_adata,
)
from skills.singlecell._lib.viz import plot_barcode_rank, plot_count_distributions

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-pseudoalign-count"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-pseudoalign-count/sc_pseudoalign_count.py"


def _barcode_metrics_df(adata) -> pd.DataFrame:
    matrix = adata.X
    return pd.DataFrame(
        {
            "barcode": adata.obs_names.astype(str),
            "total_counts": np.asarray(matrix.sum(axis=1)).ravel(),
            "detected_genes": np.asarray((matrix > 0).sum(axis=1)).ravel(),
        }
    ).sort_values("total_counts", ascending=False).reset_index(drop=True)


def _count_summary_df(adata, method: str) -> pd.DataFrame:
    barcode_df = _barcode_metrics_df(adata)
    return pd.DataFrame(
        [
            {"metric": "method", "value": method},
            {"metric": "n_cells", "value": int(adata.n_obs)},
            {"metric": "n_genes", "value": int(adata.n_vars)},
            {"metric": "median_counts_per_barcode", "value": float(barcode_df["total_counts"].median())},
            {"metric": "median_detected_genes", "value": float(barcode_df["detected_genes"].median())},
        ]
    )


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_tables(output_dir: Path, count_summary: pd.DataFrame, barcode_summary: pd.DataFrame) -> dict[str, str]:
    tables_dir = output_dir / "tables"
    figure_data_dir = output_dir / "figure_data"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "count_summary": "count_summary.csv",
        "barcode_summary": "barcode_metrics.csv",
    }
    count_summary.to_csv(tables_dir / files["count_summary"], index=False)
    barcode_summary.to_csv(tables_dir / files["barcode_summary"], index=False)
    count_summary.to_csv(figure_data_dir / files["count_summary"], index=False)
    barcode_summary.to_csv(figure_data_dir / files["barcode_summary"], index=False)
    _write_figure_data_manifest(
        output_dir,
        {
            "skill": SKILL_NAME,
            "available_files": {
                "count_summary": files["count_summary"],
                "barcode_metrics": files["barcode_summary"],
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
    command_parts.extend(["--output", str(output_dir), "--method", args.method])
    if args.reference:
        command_parts.extend(["--reference", args.reference])
    if args.t2g:
        command_parts.extend(["--t2g", args.t2g])
    if args.read2:
        command_parts.extend(["--read2", args.read2])
    if args.sample:
        command_parts.extend(["--sample", args.sample])
    if args.threads != 8:
        command_parts.extend(["--threads", str(args.threads)])
    if args.chemistry != "10xv3":
        command_parts.extend(["--chemistry", args.chemistry])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    write_repro_requirements(output_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib"])


def _write_report(output_dir: Path, *, summary: dict, input_file: str | None, artifacts: dict[str, object]) -> None:
    header = generate_report_header(
        title="Single-Cell Pseudoalign Count Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file and Path(input_file).is_file() else None,
        extra_metadata={
            "Method": summary["method"],
            "Cells": str(summary["n_cells"]),
            "Genes": str(summary["n_genes"]),
        },
    )
    lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cells retained**: {summary['n_cells']:,}",
        f"- **Genes retained**: {summary['n_genes']:,}",
        f"- **Median counts per barcode**: {summary['median_counts']:.1f}",
        f"- **Median detected genes**: {summary['median_genes']:.1f}",
        "",
        "## Preserved Artifacts\n",
    ]
    for key, value in artifacts.items():
        lines.append(f"- **{key}**: {value}")
    lines.extend(
        [
            "",
            "## Output Files\n",
            "- `standardized_input.h5ad` — downstream-ready AnnData with `layers['counts']`",
            "- `figures/barcode_rank.png` — barcode-rank curve",
            "- `figures/count_distributions.png` — count distributions",
            "- `tables/count_summary.csv` — compact run-level summary",
            "- `tables/barcode_metrics.csv` — per-barcode metrics",
            "",
            "## Recommended Next Step\n",
            "- Continue with `sc-qc` or `sc-preprocessing` on `standardized_input.h5ad`.",
        ]
    )
    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + generate_report_footer(), encoding="utf-8")


def _demo_adata():
    adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
    return adata, str(demo_path) if demo_path else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate scRNA-seq counts through simpleaf or kb-python and export a standard AnnData handoff.")
    parser.add_argument("--input", dest="input_path", help="FASTQ path or existing pseudoalign result directory / h5ad")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run built-in demo mode")
    parser.add_argument("--method", choices=["simpleaf", "kb_python"], default="simpleaf", help="Pseudoalignment backend")
    parser.add_argument("--reference", help="simpleaf index path or kallisto index path")
    parser.add_argument("--t2g", help="Transcript-to-gene map for kb-python")
    parser.add_argument("--sample", help="Choose one sample from a multi-sample FASTQ directory")
    parser.add_argument("--read2", help="Explicit mate FASTQ when --input points to one file")
    parser.add_argument("--threads", type=int, default=8, help="Backend thread count")
    parser.add_argument("--chemistry", default="10xv3", help="Chemistry / technology hint, default 10xv3")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_command: list[str] = []

    if args.demo:
        adata, input_file = _demo_adata()
        standardized, contract = standardize_count_adata(
            adata,
            skill_name=SKILL_NAME,
            method="demo",
            source_label="demo.filtered_matrix",
            warnings=[],
        )
        artifacts = {"source": "demo"}
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input path not found: {input_path}")
        input_file = str(input_path)

        if input_path.is_dir() or input_path.suffix.lower() == ".h5ad":
            try:
                resolved = inspect_pseudoalign_output(input_path, method=args.method)
            except Exception:
                resolved = None
        else:
            resolved = None

        if resolved is None:
            if not args.reference:
                raise ValueError("Real pseudoalign runs require `--reference`.")
            samples = discover_fastq_samples(input_path, read2=args.read2, sample=args.sample)
            sample = choose_fastq_sample(samples, sample=args.sample)
            if args.method == "simpleaf":
                resolved, command = run_simpleaf_quant(
                    sample,
                    index_path=args.reference,
                    chemistry=args.chemistry,
                    output_dir=output_dir,
                    threads=args.threads,
                )
                execution_command = list(command)
            else:
                if not args.t2g:
                    raise ValueError("kb-python runs require `--t2g`.")
                resolved, command = run_kb_count(
                    sample,
                    index_path=args.reference,
                    t2g_path=args.t2g,
                    technology=args.chemistry,
                    output_dir=output_dir,
                    threads=args.threads,
                )
                execution_command = list(command)

        adata = load_pseudoalign_adata(resolved)
        standardized, contract = standardize_count_adata(
            adata,
            skill_name=SKILL_NAME,
            method=args.method,
            source_label=f"{args.method}.counts",
            warnings=[],
        )
        artifacts = {
            "run_dir": str(resolved.run_dir),
            "h5ad_path": str(resolved.h5ad_path) if resolved.h5ad_path else "",
            "matrix_dir": str(resolved.matrix_dir) if resolved.matrix_dir else "",
        }

    barcode_summary = _barcode_metrics_df(standardized)
    count_summary = _count_summary_df(standardized, args.method if not args.demo else "demo")
    files = _export_tables(output_dir, count_summary, barcode_summary)
    plot_barcode_rank(barcode_summary["total_counts"].to_numpy(), output_dir)
    plot_count_distributions(standardized, output_dir)
    _write_reproducibility(output_dir, args, demo_mode=args.demo)

    output_h5ad = output_dir / "standardized_input.h5ad"
    save_h5ad(standardized, output_h5ad)

    summary = {
        "method": args.method if not args.demo else "demo",
        "n_cells": int(standardized.n_obs),
        "n_genes": int(standardized.n_vars),
        "median_counts": float(barcode_summary["total_counts"].median()),
        "median_genes": float(barcode_summary["detected_genes"].median()),
    }
    _write_report(output_dir, summary=summary, input_file=input_file, artifacts=artifacts)

    checksum = sha256_file(input_file) if input_file and Path(input_file).is_file() else ""
    result_data = {
        "method": args.method if not args.demo else "demo",
        "params": {
            "reference": args.reference or "",
            "t2g": args.t2g or "",
            "sample": args.sample or "",
            "threads": int(args.threads),
            "chemistry": args.chemistry,
        },
        "input_contract": contract,
        "artifacts": artifacts,
        "visualization": {
            "available_figure_data": {
                "count_summary": files["count_summary"],
                "barcode_metrics": files["barcode_summary"],
            }
        },
        "execution": execution_command,
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_standard_run_artifacts(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Generate or import scRNA-seq pseudoalignment counts through simpleaf or kb-python.",
        result_payload=result_payload,
        preferred_method=summary["method"],
        script_path=Path(__file__).resolve(),
        actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
    )

    print(f"\n{'=' * 60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'=' * 60}")
    print(f"  Output directory: {output_dir}")
    print(f"  Cells retained: {summary['n_cells']:,}")
    print(f"  Genes retained: {summary['n_genes']:,}")
    print(f"  Standardized output: {output_h5ad}")


if __name__ == "__main__":
    main()
