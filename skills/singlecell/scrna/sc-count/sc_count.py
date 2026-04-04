#!/usr/bin/env python3
"""scRNA-seq count generation with Cell Ranger or STARsolo."""

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
from skills.singlecell._lib.export import save_h5ad, write_h5ad_aliases
from skills.singlecell._lib.pseudoalign import (
    inspect_pseudoalign_output,
    load_pseudoalign_adata,
    run_kb_count,
    run_simpleaf_quant,
)
from skills.singlecell._lib.upstream import (
    auto_reference_path,
    auto_t2g_path,
    choose_fastq_sample,
    detect_cellranger_outs,
    detect_starsolo_output,
    discover_fastq_samples,
    ensure_existing_path,
    guess_starsolo_whitelist,
    inspect_cellranger_run,
    inspect_starsolo_run,
    load_count_adata_from_artifacts,
    load_raw_count_adata_from_artifacts,
    parse_summary_table,
    reference_setup_guidance,
    run_cellranger_count,
    run_starsolo_count,
    standardize_count_adata,
    t2g_setup_guidance,
    whitelist_setup_guidance,
)
from skills.singlecell._lib.viz import (
    plot_barcode_rank,
    plot_count_complexity_scatter,
    plot_count_distributions,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-count"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-count/sc_count.py"


def _recommended_reference_dir(method: str) -> Path:
    return {
        "cellranger": Path("resources/singlecell/references/cellranger"),
        "starsolo": Path("resources/singlecell/references/starsolo"),
        "simpleaf": Path("resources/singlecell/references/simpleaf"),
        "kb_python": Path("resources/singlecell/references/kb"),
    }[method]


def _resolve_reference_arg(method: str, reference: str | None) -> Path | None:
    if reference:
        return ensure_existing_path(
            reference,
            flag="--reference",
            label=f"{method} reference",
            recommended_dir=_recommended_reference_dir(method),
            expect_directory=method in {"cellranger", "starsolo"},
        )
    inferred = auto_reference_path(method)
    if inferred is not None:
        logger.info("Using project-local %s reference: %s", method, inferred)
    return inferred


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_figures_manifest(output_dir: Path, plots: list[dict]) -> None:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "recipe_id": "standard-sc-count-gallery",
        "skill_name": SKILL_NAME,
        "title": "Single-cell counting gallery",
        "description": "Canonical counting diagnostics for retained barcodes.",
        "backend": "python",
        "plots": plots,
    }
    (figures_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _barcode_metrics_df(adata) -> pd.DataFrame:
    matrix = adata.X
    total_counts = np.asarray(matrix.sum(axis=1)).ravel()
    detected_genes = np.asarray((matrix > 0).sum(axis=1)).ravel()
    return (
        pd.DataFrame(
            {
                "barcode": adata.obs_names.astype(str),
                "total_counts": total_counts,
                "detected_genes": detected_genes,
            }
        )
        .sort_values("total_counts", ascending=False)
        .reset_index(drop=True)
    )


def _count_summary_df(adata, method: str, backend_summary: dict[str, object]) -> pd.DataFrame:
    barcode_df = _barcode_metrics_df(adata)
    rows = [
        {"metric": "method", "value": method},
        {"metric": "n_cells", "value": int(adata.n_obs)},
        {"metric": "n_genes", "value": int(adata.n_vars)},
        {"metric": "median_counts_per_barcode", "value": float(barcode_df["total_counts"].median())},
        {"metric": "median_detected_genes", "value": float(barcode_df["detected_genes"].median())},
    ]
    for key, value in backend_summary.items():
        rows.append({"metric": str(key), "value": value})
    return pd.DataFrame(rows)


def _export_tables(output_dir: Path, count_summary: pd.DataFrame, barcode_metrics: pd.DataFrame, backend_summary: dict[str, object]) -> dict[str, str]:
    tables_dir = output_dir / "tables"
    figure_data_dir = output_dir / "figure_data"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    table_files = {
        "count_summary": "count_summary.csv",
        "barcode_metrics": "barcode_metrics.csv",
        "backend_summary": "backend_summary.csv",
    }
    count_summary.to_csv(tables_dir / table_files["count_summary"], index=False)
    barcode_metrics.to_csv(tables_dir / table_files["barcode_metrics"], index=False)
    pd.DataFrame({"metric": list(backend_summary.keys()), "value": list(backend_summary.values())}).to_csv(
        tables_dir / table_files["backend_summary"], index=False
    )

    count_summary.to_csv(figure_data_dir / table_files["count_summary"], index=False)
    barcode_metrics.to_csv(figure_data_dir / table_files["barcode_metrics"], index=False)
    _write_figure_data_manifest(
        output_dir,
        {
            "skill": SKILL_NAME,
            "recipe_id": "standard-sc-count-gallery",
            "available_files": {
                "count_summary": table_files["count_summary"],
                "barcode_metrics": table_files["barcode_metrics"],
            },
        },
    )
    return table_files


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
    if getattr(args, "t2g", None):
        command_parts.extend(["--t2g", args.t2g])
    if args.sample:
        command_parts.extend(["--sample", args.sample])
    if args.read2:
        command_parts.extend(["--read2", args.read2])
    if args.threads != 8:
        command_parts.extend(["--threads", str(args.threads)])
    if args.chemistry != "auto":
        command_parts.extend(["--chemistry", args.chemistry])
    if args.whitelist:
        command_parts.extend(["--whitelist", args.whitelist])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    write_repro_requirements(output_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib"])


def _report_artifact_lines(artifacts) -> list[str]:
    if artifacts is None:
        return ["- Demo mode: no external counting backend was executed."]
    lines = [f"- **Backend run directory**: `{artifacts.run_dir}`"]
    if hasattr(artifacts, "filtered_h5") and artifacts.filtered_h5:
        lines.append(f"- **Filtered H5**: `{artifacts.filtered_h5}`")
    if hasattr(artifacts, "filtered_matrix_dir") and artifacts.filtered_matrix_dir:
        lines.append(f"- **Filtered MEX**: `{artifacts.filtered_matrix_dir}`")
    if hasattr(artifacts, "raw_h5") and artifacts.raw_h5:
        lines.append(f"- **Raw H5**: `{artifacts.raw_h5}`")
    if hasattr(artifacts, "raw_matrix_dir") and artifacts.raw_matrix_dir:
        lines.append(f"- **Raw MEX**: `{artifacts.raw_matrix_dir}`")
    if hasattr(artifacts, "bam_path") and artifacts.bam_path:
        lines.append(f"- **BAM**: `{artifacts.bam_path}`")
    if hasattr(artifacts, "summary_csv") and artifacts.summary_csv:
        lines.append(f"- **Summary CSV**: `{artifacts.summary_csv}`")
    if hasattr(artifacts, "h5ad_path") and artifacts.h5ad_path:
        lines.append(f"- **Imported H5AD**: `{artifacts.h5ad_path}`")
    if hasattr(artifacts, "matrix_dir") and artifacts.matrix_dir:
        lines.append(f"- **Imported matrix directory**: `{artifacts.matrix_dir}`")
    return lines


def _write_report(
    output_dir: Path,
    *,
    summary: dict,
    input_file: str | None,
    backend_summary: dict[str, object],
    artifacts,
) -> None:
    header = generate_report_header(
        title="Single-Cell Counting Report",
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
        f"- **Cells retained in filtered matrix**: {summary['n_cells']:,}",
        f"- **Genes retained in filtered matrix**: {summary['n_genes']:,}",
        f"- **Median counts per barcode**: {summary['median_counts']:.1f}",
        f"- **Median detected genes**: {summary['median_genes']:.1f}",
        "",
        "## Backend Artifacts\n",
    ]
    lines.extend(_report_artifact_lines(artifacts))

    lines.extend(["", "## Parsed Backend Summary\n"])
    if backend_summary:
        for key, value in backend_summary.items():
            lines.append(f"- **{key}**: {value}")
    else:
        lines.append("- No backend summary table was available.")

    lines.extend(
        [
            "",
            "## Output Files\n",
            "- `processed.h5ad` — downstream-ready AnnData with `layers['counts']`",
            "- `standardized_input.h5ad` — compatibility alias pointing to the same downstream-ready object",
            "- `figures/barcode_rank.png` — barcode-rank curve for filtered and optional raw counts",
            "- `figures/count_distributions.png` — total-count and detected-gene distributions",
            "- `figures/count_complexity_scatter.png` — counts versus detected genes across retained barcodes",
            "- `tables/count_summary.csv` — compact run-level summary",
            "- `tables/barcode_metrics.csv` — per-barcode count summary",
            "- `figures/manifest.json` — standard counting gallery manifest",
            "- `figure_data/manifest.json` — plot-ready data manifest",
            "",
            "## Recommended Next Step\n",
            "- Continue with `sc-qc` or `sc-preprocessing` on `processed.h5ad`.",
        ]
    )
    if artifacts is not None and getattr(artifacts, "method", "") == "cellranger" and getattr(artifacts, "bam_path", None):
        lines.append("- For RNA velocity from Cell Ranger outputs, continue with `sc-velocity-prep --method velocyto`.")
    if artifacts is not None and getattr(artifacts, "raw_h5", None):
        lines.append("- For ambient RNA removal with CellBender, preserve the raw `.h5` path shown above.")

    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + generate_report_footer(), encoding="utf-8")


def _demo_adata():
    adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
    return adata, str(demo_path) if demo_path else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate scRNA-seq count matrices with mainstream counting backends.")
    parser.add_argument("--input", dest="input_path", help="FASTQ path or existing Cell Ranger / STARsolo output directory")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run built-in demo mode")
    parser.add_argument(
        "--method",
        choices=["cellranger", "starsolo", "simpleaf", "kb_python"],
        default="cellranger",
        help="Counting backend",
    )
    parser.add_argument("--reference", help="Backend reference path: Cell Ranger transcriptome, STAR genome dir, simpleaf index, or kallisto index")
    parser.add_argument("--t2g", help="Transcript-to-gene map required for kb-python runs")
    parser.add_argument("--sample", help="Choose one sample from a multi-sample FASTQ directory")
    parser.add_argument("--read2", help="Explicit mate file when --input points to one FASTQ file")
    parser.add_argument("--threads", type=int, default=8, help="Backend thread count")
    parser.add_argument("--chemistry", default="auto", help="Chemistry hint; STARsolo currently supports 10xv2, 10xv3, and 10xv4")
    parser.add_argument("--whitelist", help="STARsolo barcode whitelist file")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    execution = None
    artifacts = None
    backend_summary: dict[str, object] = {}
    used_reference = ""
    used_t2g = ""
    used_whitelist = ""

    if args.demo:
        adata, input_file = _demo_adata()
        standardized, contract = standardize_count_adata(
            adata,
            skill_name=SKILL_NAME,
            method="demo",
            source_label="demo.filtered_matrix",
            warnings=[],
        )
        raw_adata = adata.copy()
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input path not found: {input_path}")
        input_file = str(input_path)

        reference_path = _resolve_reference_arg(args.method, args.reference)
        used_reference = str(reference_path) if reference_path is not None else ""
        t2g_path = None
        if args.method == "kb_python":
            if args.t2g:
                t2g_path = ensure_existing_path(
                    args.t2g,
                    flag="--t2g",
                    label="kb transcript-to-gene map",
                    recommended_dir=Path("resources/singlecell/references/kb"),
                    expect_directory=False,
                )
            else:
                t2g_path = auto_t2g_path()
                if t2g_path is not None:
                    logger.info("Using project-local kb t2g map: %s", t2g_path)
            used_t2g = str(t2g_path) if t2g_path is not None else ""

        if args.whitelist:
            whitelist_path = ensure_existing_path(
                args.whitelist,
                flag="--whitelist",
                label="STARsolo barcode whitelist",
                recommended_dir=Path("resources/singlecell/references/whitelists"),
                expect_directory=False,
            )
        else:
            whitelist_path = None
        used_whitelist = str(whitelist_path) if whitelist_path is not None else ""

        if args.method == "cellranger" and detect_cellranger_outs(input_path):
            artifacts = inspect_cellranger_run(input_path)
        elif args.method == "starsolo" and detect_starsolo_output(input_path):
            artifacts = inspect_starsolo_run(input_path)
        elif args.method in {"simpleaf", "kb_python"} and (input_path.is_dir() or input_path.suffix.lower() == ".h5ad"):
            try:
                artifacts = inspect_pseudoalign_output(input_path, method=args.method)
            except Exception:
                artifacts = None

        if artifacts is None and not args.demo:
            if reference_path is None:
                raise ValueError(
                    f"`sc-count --method {args.method}` requires a local reference path. "
                    f"Pass `--reference /abs/path/...`, or keep one under `{_recommended_reference_dir(args.method)}` so OmicsClaw can auto-detect it.\n\n"
                    f"{reference_setup_guidance(args.method)}"
                )
            samples = discover_fastq_samples(input_path, read2=args.read2, sample=args.sample)
            sample = choose_fastq_sample(samples, sample=args.sample)

            if args.method == "cellranger":
                artifacts, execution = run_cellranger_count(
                    sample,
                    fastq_dir=input_path.parent if input_path.is_file() else input_path,
                    reference=reference_path,
                    output_dir=output_dir,
                    threads=args.threads,
                    chemistry=args.chemistry,
                )
            elif args.method == "starsolo":
                if args.chemistry == "auto":
                    raise ValueError("STARsolo runs require an explicit `--chemistry` value such as `10xv3`.")
                whitelist = whitelist_path or guess_starsolo_whitelist(reference_path, args.chemistry)
                if whitelist is None:
                    raise ValueError(
                        "Could not infer a compatible STARsolo whitelist. "
                        "Pass `--whitelist /abs/path/to/3M-february-2018.txt`, or keep the whitelist under "
                        "`resources/singlecell/references/whitelists/`.\n\n"
                        f"{whitelist_setup_guidance()}"
                    )
                used_whitelist = str(whitelist)
                artifacts, execution = run_starsolo_count(
                    sample,
                    reference=reference_path,
                    output_dir=output_dir,
                    threads=args.threads,
                    chemistry=args.chemistry,
                    whitelist=whitelist,
                    features=("Gene",),
                )
            elif args.method == "simpleaf":
                artifacts, execution = run_simpleaf_quant(
                    sample,
                    index_path=reference_path,
                    chemistry="10xv3" if args.chemistry == "auto" else args.chemistry,
                    output_dir=output_dir,
                    threads=args.threads,
                )
            else:
                if t2g_path is None:
                    raise ValueError(
                        "kb-python runs require a transcript-to-gene map. "
                        "Pass `--t2g /abs/path/to/t2g.tsv`, or keep one under `resources/singlecell/references/kb/`.\n\n"
                        f"{t2g_setup_guidance()}"
                    )
                artifacts, execution = run_kb_count(
                    sample,
                    index_path=reference_path,
                    t2g_path=t2g_path,
                    technology="10xv3" if args.chemistry == "auto" else args.chemistry,
                    output_dir=output_dir,
                    threads=args.threads,
                )

        if args.method in {"simpleaf", "kb_python"}:
            adata = load_pseudoalign_adata(artifacts)
            raw_adata = adata.copy()
            backend_summary = {}
        else:
            adata = load_count_adata_from_artifacts(artifacts)
            raw_adata = load_raw_count_adata_from_artifacts(artifacts) or adata.copy()
            backend_summary = parse_summary_table(artifacts.summary_csv or artifacts.log_path)
        standardized, contract = standardize_count_adata(
            adata,
            skill_name=SKILL_NAME,
            method=args.method,
            source_label=f"{args.method}.filtered_matrix",
            warnings=[],
        )
        if args.method in {"simpleaf", "kb_python"}:
            standardized.uns["omicsclaw_count_artifacts"] = {
                "method": artifacts.method,
                "run_dir": str(artifacts.run_dir),
                "h5ad_path": str(artifacts.h5ad_path) if artifacts.h5ad_path else "",
                "matrix_dir": str(artifacts.matrix_dir) if artifacts.matrix_dir else "",
            }
        else:
            standardized.uns["omicsclaw_count_artifacts"] = {
                "method": artifacts.method,
                "run_dir": str(artifacts.run_dir),
                "filtered_matrix_dir": str(artifacts.filtered_matrix_dir) if artifacts.filtered_matrix_dir else "",
                "filtered_h5": str(artifacts.filtered_h5) if artifacts.filtered_h5 else "",
                "raw_matrix_dir": str(artifacts.raw_matrix_dir) if artifacts.raw_matrix_dir else "",
                "raw_h5": str(artifacts.raw_h5) if artifacts.raw_h5 else "",
                "bam_path": str(artifacts.bam_path) if artifacts.bam_path else "",
                "summary_csv": str(artifacts.summary_csv) if artifacts.summary_csv else "",
            }

    barcode_metrics = _barcode_metrics_df(standardized)
    count_summary = _count_summary_df(standardized, args.method if not args.demo else "demo", backend_summary)
    table_files = _export_tables(output_dir, count_summary, barcode_metrics, backend_summary)

    plot_count_distributions(standardized, output_dir)
    raw_counts = np.asarray(raw_adata.X.sum(axis=1)).ravel() if raw_adata is not None else None
    plot_barcode_rank(barcode_metrics["total_counts"].to_numpy(), output_dir, raw_counts=raw_counts)
    plot_count_complexity_scatter(barcode_metrics, output_dir)
    _write_figures_manifest(
        output_dir,
        [
            {
                "plot_id": "barcode_rank",
                "role": "overview",
                "backend": "python",
                "renderer": "plot_barcode_rank",
                "filename": "barcode_rank.png",
                "title": "Barcode rank curve",
                "description": "Filtered barcode ranks with optional raw background.",
                "status": "rendered",
                "path": str(output_dir / "figures" / "barcode_rank.png"),
            },
            {
                "plot_id": "count_distributions",
                "role": "diagnostic",
                "backend": "python",
                "renderer": "plot_count_distributions",
                "filename": "count_distributions.png",
                "title": "Count distributions",
                "description": "Total counts and detected genes across retained barcodes.",
                "status": "rendered",
                "path": str(output_dir / "figures" / "count_distributions.png"),
            },
            {
                "plot_id": "count_complexity_scatter",
                "role": "diagnostic",
                "backend": "python",
                "renderer": "plot_count_complexity_scatter",
                "filename": "count_complexity_scatter.png",
                "title": "Count complexity per barcode",
                "description": "Counts versus detected genes for retained barcodes.",
                "status": "rendered",
                "path": str(output_dir / "figures" / "count_complexity_scatter.png"),
            },
        ],
    )

    _write_reproducibility(output_dir, args, demo_mode=args.demo)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(standardized, output_h5ad)
    alias_paths = write_h5ad_aliases(output_h5ad, [output_dir / "standardized_input.h5ad"])

    summary = {
        "method": args.method if not args.demo else "demo",
        "n_cells": int(standardized.n_obs),
        "n_genes": int(standardized.n_vars),
        "median_counts": float(barcode_metrics["total_counts"].median()),
        "median_genes": float(barcode_metrics["detected_genes"].median()),
    }
    _write_report(output_dir, summary=summary, input_file=input_file, backend_summary=backend_summary, artifacts=artifacts)

    checksum = sha256_file(input_file) if input_file and Path(input_file).is_file() else ""
    result_data = {
        "method": args.method if not args.demo else "demo",
        "params": {
            "reference": used_reference,
            "t2g": used_t2g,
            "sample": args.sample or "",
            "threads": int(args.threads),
            "chemistry": args.chemistry,
            "whitelist": used_whitelist,
        },
        "backend_summary": backend_summary,
        "input_contract": contract,
        "matrix_contract": standardized.uns.get("omicsclaw_matrix_contract", {}),
        "output_h5ad": "processed.h5ad",
        "summary_tables": table_files,
        "visualization": {
            "recipe_id": "standard-sc-count-gallery",
            "available_figure_data": {
                "count_summary": table_files["count_summary"],
                "barcode_metrics": table_files["barcode_metrics"],
            }
        },
        "artifacts": standardized.uns.get("omicsclaw_count_artifacts", {}),
        "output_files": {
            "processed_h5ad": str(output_h5ad),
            "compatibility_aliases": [str(path) for path in alias_paths],
        },
        "execution": list(execution.command) if execution is not None else [],
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_standard_run_artifacts(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Generate single-cell count matrices with Cell Ranger, STARsolo, SimpleAF / Alevin-fry, or kb-python and export a downstream-ready standardized AnnData.",
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
    if artifacts is not None:
        print(f"  Backend artifacts: {artifacts.run_dir}")


if __name__ == "__main__":
    main()
