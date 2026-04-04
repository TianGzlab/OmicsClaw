#!/usr/bin/env python3
"""Single-cell FASTQ QC wrapper with FastQC/MultiQC integration."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_repro_requirements,
    write_result_json,
    write_standard_run_artifacts,
)
from skills.singlecell._lib.upstream import (
    choose_fastq_sample,
    discover_fastq_samples,
    run_fastqc,
    run_multiqc,
    summarize_fastq_samples,
    tool_available,
)
from skills.singlecell._lib.viz import (
    plot_fastq_file_quality,
    plot_fastq_per_base_quality,
    plot_fastq_read_structure,
    plot_fastq_sample_summary,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-fastq-qc"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-fastq-qc/sc_fastq_qc.py"


def _demo_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    per_file = pd.DataFrame(
        [
            {
                "sample_id": "pbmc_demo",
                "read_label": "R1",
                "file": "pbmc_demo_R1.fastq.gz",
                "path": "demo://pbmc_demo_R1.fastq.gz",
                "sampled_reads": 12000,
                "mean_read_length": 28.0,
                "median_read_length": 28.0,
                "gc_pct": 48.5,
                "q20_pct": 99.1,
                "q30_pct": 95.3,
                "mean_quality": 34.8,
                "adapter_seed_pct": 0.2,
            },
            {
                "sample_id": "pbmc_demo",
                "read_label": "R2",
                "file": "pbmc_demo_R2.fastq.gz",
                "path": "demo://pbmc_demo_R2.fastq.gz",
                "sampled_reads": 12000,
                "mean_read_length": 91.0,
                "median_read_length": 91.0,
                "gc_pct": 46.7,
                "q20_pct": 98.7,
                "q30_pct": 93.8,
                "mean_quality": 34.1,
                "adapter_seed_pct": 0.8,
            },
        ]
    )
    per_base_rows = []
    for read_label, base_quality in (("R1", 35.6), ("R2", 34.2)):
        for position in range(1, 31 if read_label == "R1" else 92):
            drop = 0.02 * max(position - 20, 0)
            per_base_rows.append(
                {
                    "sample_id": "pbmc_demo",
                    "read_label": read_label,
                    "file": f"pbmc_demo_{read_label}.fastq.gz",
                    "position": position,
                    "mean_quality": max(base_quality - drop, 30.5 if read_label == "R2" else 33.5),
                }
            )
    per_base = pd.DataFrame(per_base_rows)
    per_sample = (
        per_file.groupby("sample_id", dropna=False)
        .agg(
            files=("file", "count"),
            sampled_reads=("sampled_reads", "sum"),
            mean_read_length=("mean_read_length", "mean"),
            gc_pct=("gc_pct", "mean"),
            q20_pct=("q20_pct", "mean"),
            q30_pct=("q30_pct", "mean"),
            mean_quality=("mean_quality", "mean"),
            adapter_seed_pct=("adapter_seed_pct", "mean"),
        )
        .reset_index()
    )
    return per_file, per_base, per_sample


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_figures_manifest(output_dir: Path, plots: list[dict]) -> None:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "recipe_id": "standard-sc-fastq-qc-gallery",
        "skill_name": SKILL_NAME,
        "title": "Single-cell FASTQ QC gallery",
        "description": "Canonical read-level QC overview for scRNA FASTQ inputs.",
        "backend": "python",
        "plots": plots,
    }
    (figures_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_tables(output_dir: Path, per_file: pd.DataFrame, per_base: pd.DataFrame, per_sample: pd.DataFrame) -> dict[str, str]:
    tables_dir = output_dir / "tables"
    figure_data_dir = output_dir / "figure_data"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    table_files = {
        "per_file": "fastq_per_file_summary.csv",
        "per_sample": "fastq_per_sample_summary.csv",
        "per_base": "fastq_per_base_quality.csv",
    }
    per_file.to_csv(tables_dir / table_files["per_file"], index=False)
    per_sample.to_csv(tables_dir / table_files["per_sample"], index=False)
    per_base.to_csv(tables_dir / table_files["per_base"], index=False)

    per_sample.to_csv(figure_data_dir / table_files["per_sample"], index=False)
    per_base.to_csv(figure_data_dir / table_files["per_base"], index=False)
    _write_figure_data_manifest(
        output_dir,
        {
            "skill": SKILL_NAME,
            "recipe_id": "standard-sc-fastq-qc-gallery",
            "available_files": {
                "fastq_per_file_summary": table_files["per_file"],
                "fastq_per_sample_summary": table_files["per_sample"],
                "fastq_per_base_quality": table_files["per_base"],
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
    if args.read2:
        command_parts.extend(["--read2", args.read2])
    if args.sample:
        command_parts.extend(["--sample", args.sample])
    if args.max_reads != 20000:
        command_parts.extend(["--max-reads", str(args.max_reads)])
    if args.threads != 4:
        command_parts.extend(["--threads", str(args.threads)])
    command_parts.extend(["--output", str(output_dir)])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    write_repro_requirements(output_dir, ["numpy", "pandas", "matplotlib", "scanpy"])


def _write_report(
    output_dir: Path,
    *,
    summary: dict,
    input_file: str | None,
    per_sample: pd.DataFrame,
    fastqc_execution,
    multiqc_execution,
) -> None:
    header = generate_report_header(
        title="Single-Cell FASTQ QC Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file and Path(input_file).is_file() else None,
        extra_metadata={
            "Samples": str(summary["n_samples"]),
            "FASTQ files": str(summary["n_fastq_files"]),
            "FastQC available": str(summary["fastqc_available"]),
            "MultiQC available": str(summary["multiqc_available"]),
        },
    )
    lines = [
        "## Summary\n",
        f"- **Samples summarized**: {summary['n_samples']}",
        f"- **FASTQ files summarized**: {summary['n_fastq_files']}",
        f"- **Mean sample Q30**: {summary['mean_q30_pct']:.2f}%",
        f"- **Mean sample GC**: {summary['mean_gc_pct']:.2f}%",
        f"- **FastQC used**: {summary['fastqc_used']}",
        f"- **MultiQC used**: {summary['multiqc_used']}",
        "",
        "## Per-Sample Overview\n",
    ]
    for _, row in per_sample.iterrows():
        lines.extend(
            [
                f"### {row['sample_id']}\n",
                f"- **FASTQ files**: {int(row['files'])}",
                f"- **Sampled reads**: {int(row['sampled_reads']):,}",
                f"- **Mean read length**: {row['mean_read_length']:.1f}",
                f"- **GC%**: {row['gc_pct']:.2f}",
                f"- **Q20%**: {row['q20_pct']:.2f}",
                f"- **Q30%**: {row['q30_pct']:.2f}",
                f"- **Adapter-seed reads**: {row['adapter_seed_pct']:.2f}%",
                "",
            ]
        )

    lines.extend(
        [
            "## External Tool Artifacts\n",
            f"- **FastQC binary available**: {summary['fastqc_available']}",
            f"- **MultiQC binary available**: {summary['multiqc_available']}",
        ]
    )
    if fastqc_execution is not None:
        lines.append(f"- **FastQC command**: `{' '.join(fastqc_execution.command)}`")
    if multiqc_execution is not None:
        lines.append(f"- **MultiQC command**: `{' '.join(multiqc_execution.command)}`")

    lines.extend(
        [
            "",
            "## Output Files\n",
            "- `figures/fastq_q30_summary.png` — sample-level Q30 and GC overview",
            "- `figures/per_base_quality.png` — per-base mean quality curves",
            "- `figures/fastq_file_quality.png` — per-file quality versus adapter and GC/read-length diagnostics",
            "- `figures/fastq_read_structure.png` — per-file read length and adapter-seed overview",
            "- `tables/fastq_per_file_summary.csv` — per-FASTQ sampled summary",
            "- `tables/fastq_per_sample_summary.csv` — per-sample sampled summary",
            "- `tables/fastq_per_base_quality.csv` — per-position sampled quality values",
            "- `artifacts/fastqc/` and `artifacts/multiqc/` — external tool outputs when those tools are installed",
            "",
            "## Recommended Next Step\n",
            "- If read quality looks acceptable, continue with `sc-count` for Cell Ranger or STARsolo counting.",
        ]
    )

    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + generate_report_footer(), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quality control for raw scRNA-seq FASTQ files.")
    parser.add_argument("--input", dest="input_path", help="FASTQ file or directory")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run built-in demo mode")
    parser.add_argument("--read2", help="Optional read 2 FASTQ when --input points to one file")
    parser.add_argument("--sample", help="Choose one sample from a multi-sample FASTQ directory")
    parser.add_argument("--threads", type=int, default=4, help="Thread count for external FastQC runs")
    parser.add_argument("--max-reads", type=int, default=20000, help="Per-FASTQ read sampling depth for the Python fallback summary")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        per_file_df, per_base_df, per_sample_df = _demo_tables()
        input_file = None
        selected_sample = None
        fastqc_execution = None
        multiqc_execution = None
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        samples = discover_fastq_samples(args.input_path, read2=args.read2, sample=args.sample)
        selected_sample = choose_fastq_sample(samples, sample=args.sample)
        samples = [selected_sample]
        per_file_df, per_base_df, per_sample_df = summarize_fastq_samples(samples, max_reads_per_file=args.max_reads)
        input_file = str(Path(args.input_path))

        fastqc_output = output_dir / "artifacts" / "fastqc"
        multiqc_output = output_dir / "artifacts" / "multiqc"
        fastqc_execution = run_fastqc(selected_sample.all_files(), fastqc_output, threads=args.threads)
        multiqc_execution = run_multiqc(fastqc_output, multiqc_output) if fastqc_execution is not None else None

    plot_fastq_sample_summary(per_sample_df, output_dir)
    plot_fastq_per_base_quality(per_base_df, output_dir)
    plot_fastq_file_quality(per_file_df, output_dir)
    plot_fastq_read_structure(per_file_df, output_dir)
    _write_figures_manifest(
        output_dir,
        [
            {
                "plot_id": "fastq_q30_summary",
                "role": "overview",
                "backend": "python",
                "renderer": "plot_fastq_sample_summary",
                "filename": "fastq_q30_summary.png",
                "title": "FASTQ sample-level quality overview",
                "description": "Sample-level Q30 and GC summary.",
                "status": "rendered",
                "path": str((output_dir / "figures" / "fastq_q30_summary.png")),
            },
            {
                "plot_id": "per_base_quality",
                "role": "diagnostic",
                "backend": "python",
                "renderer": "plot_fastq_per_base_quality",
                "filename": "per_base_quality.png",
                "title": "Per-base mean quality",
                "description": "Per-position mean quality across FASTQ files.",
                "status": "rendered",
                "path": str((output_dir / "figures" / "per_base_quality.png")),
            },
            {
                "plot_id": "fastq_file_quality",
                "role": "diagnostic",
                "backend": "python",
                "renderer": "plot_fastq_file_quality",
                "filename": "fastq_file_quality.png",
                "title": "Per-file quality diagnostics",
                "description": "Per-file Q30, adapter burden, read length, and GC relationships.",
                "status": "rendered",
                "path": str((output_dir / "figures" / "fastq_file_quality.png")),
            },
            {
                "plot_id": "fastq_read_structure",
                "role": "diagnostic",
                "backend": "python",
                "renderer": "plot_fastq_read_structure",
                "filename": "fastq_read_structure.png",
                "title": "Read structure by FASTQ file",
                "description": "Mean read length and adapter-seed burden by FASTQ file.",
                "status": "rendered",
                "path": str((output_dir / "figures" / "fastq_read_structure.png")),
            },
        ],
    )
    table_files = _export_tables(output_dir, per_file_df, per_base_df, per_sample_df)
    _write_reproducibility(output_dir, args, demo_mode=args.demo)

    summary = {
        "method": "fastqc",
        "n_samples": int(per_sample_df.shape[0]),
        "n_fastq_files": int(per_file_df.shape[0]),
        "mean_q30_pct": float(per_sample_df["q30_pct"].mean()),
        "mean_gc_pct": float(per_sample_df["gc_pct"].mean()),
        "fastqc_available": tool_available("fastqc"),
        "multiqc_available": tool_available("multiqc"),
        "fastqc_used": bool(fastqc_execution),
        "multiqc_used": bool(multiqc_execution),
    }
    _write_report(
        output_dir,
        summary=summary,
        input_file=input_file,
        per_sample=per_sample_df,
        fastqc_execution=fastqc_execution,
        multiqc_execution=multiqc_execution,
    )

    result_data = {
        "method": "fastqc",
        "selected_sample": selected_sample.sample_id if selected_sample is not None else "demo",
        "params": {
            "sample": args.sample or "",
            "threads": int(args.threads),
            "max_reads": int(args.max_reads),
        },
        "summary_tables": {
            "per_file": table_files["per_file"],
            "per_sample": table_files["per_sample"],
            "per_base": table_files["per_base"],
        },
        "visualization": {
            "recipe_id": "standard-sc-fastq-qc-gallery",
            "available_figure_data": {
                "fastq_per_file_summary": table_files["per_file"],
                "fastq_per_sample_summary": table_files["per_sample"],
                "fastq_per_base_quality": table_files["per_base"],
            }
        },
        "external_tools": {
            "fastqc_available": tool_available("fastqc"),
            "multiqc_available": tool_available("multiqc"),
            "fastqc_command": list(fastqc_execution.command) if fastqc_execution else [],
            "multiqc_command": list(multiqc_execution.command) if multiqc_execution else [],
        },
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, "")
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_standard_run_artifacts(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Quality control for raw single-cell FASTQ files using FastQC and MultiQC when available.",
        result_payload=result_payload,
        preferred_method="fastqc",
        script_path=Path(__file__).resolve(),
        actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
    )

    print(f"\n{'=' * 60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'=' * 60}")
    print(f"  Output directory: {output_dir}")
    print(f"  Samples summarized: {summary['n_samples']}")
    print(f"  FASTQ files summarized: {summary['n_fastq_files']}")
    print(f"  Mean sample Q30: {summary['mean_q30_pct']:.2f}%")
    print(f"  FastQC used: {summary['fastqc_used']}")
    print(f"  MultiQC used: {summary['multiqc_used']}")


if __name__ == "__main__":
    main()
