#!/usr/bin/env python3
"""bulkrna-read-qc — FASTQ quality assessment for bulk RNA-seq.

Python reimplementation of core FastQC metrics: per-base quality,
GC content, adapter detection, read length, Q20/Q30 rates.

Usage:
    python bulkrna_read_qc.py --input reads.fastq --output results/
    python bulkrna_read_qc.py --demo --output /tmp/read_qc_demo
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path

import sys
_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))
from skills._sdk.report import (
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import write_result_json

logger = logging.getLogger(__name__)

SKILL_NAME = "bulkrna-read-qc"
SKILL_VERSION = "0.3.0"

COMMON_ADAPTERS = {
    "Illumina_TruSeq": "AGATCGGAAGAGC",
    "Nextera": "CTGTCTCTTATACACATCT",
    "Small_RNA": "TGGAATTCTCGG",
}


def generate_figures(output_dir: Path, metrics: dict) -> list[str]:
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    # 1. Per-base quality
    per_base = metrics["per_base"]
    positions = [p["position"] for p in per_base]
    means = [p["mean"] for p in per_base]
    q25s = [p["q25"] for p in per_base]
    q75s = [p["q75"] for p in per_base]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.fill_between(positions, q25s, q75s, alpha=0.3, color="#4878CF", label="Q25-Q75")
    ax.plot(positions, means, color="#4878CF", linewidth=1.5, label="Mean quality")
    ax.axhline(30, color="#5BA05B", ls="--", lw=0.8, alpha=0.7, label="Q30")
    ax.axhline(20, color="#E8A02F", ls="--", lw=0.8, alpha=0.7, label="Q20")
    ax.set_xlabel("Position in Read (bp)")
    ax.set_ylabel("Phred Quality Score")
    ax.set_title("Per-Base Sequence Quality")
    ax.legend(fontsize=8)
    ax.set_ylim(0, 42)
    fig.tight_layout()
    p = fig_dir / "per_base_quality.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 2. GC content
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(metrics["gc_fracs"], bins=50, color="#5BA05B", alpha=0.7, edgecolor="white")
    ax.axvline(np.mean(metrics["gc_fracs"]), color="#E84D60", ls="--", lw=1.5,
               label=f"Mean GC = {metrics['mean_gc']:.1f}%")
    ax.set_xlabel("GC Fraction")
    ax.set_ylabel("Number of Reads")
    ax.set_title("GC Content Distribution")
    ax.legend()
    fig.tight_layout()
    p = fig_dir / "gc_content.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 3. Read length distribution
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(metrics["read_lengths"], bins=50, color="#9467BD", alpha=0.7, edgecolor="white")
    ax.set_xlabel("Read Length (bp)")
    ax.set_ylabel("Count")
    ax.set_title("Read Length Distribution")
    fig.tight_layout()
    p = fig_dir / "read_length_distribution.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 4. Quality score distribution
    fig, ax = plt.subplots(figsize=(7, 5))
    q_arr = np.array(metrics["all_quals"])
    ax.hist(q_arr, bins=range(0, 43), color="#E8A02F", alpha=0.7, edgecolor="white")
    ax.axvline(20, color="#E84D60", ls="--", label="Q20")
    ax.axvline(30, color="#5BA05B", ls="--", label="Q30")
    ax.set_xlabel("Quality Score (Phred)")
    ax.set_ylabel("Count")
    ax.set_title("Quality Score Distribution")
    ax.legend()
    fig.tight_layout()
    p = fig_dir / "quality_score_distribution.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    return paths


def write_report(output_dir: Path, metrics: dict, params: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    header = generate_report_header(
        title="Bulk RNA-seq FASTQ Quality Report",
        skill_name=SKILL_NAME,
    )

    body_lines = [
        "## Summary\n",
        f"- **Total reads**: {metrics['n_reads']:,}",
        f"- **Mean read length**: {metrics['mean_read_length']:.0f} bp",
        f"- **Mean quality**: {metrics['mean_quality']:.1f} (Phred)",
        f"- **Q20 rate**: {metrics['q20_rate']:.1f}%",
        f"- **Q30 rate**: {metrics['q30_rate']:.1f}%",
        f"- **Mean GC content**: {metrics['mean_gc']:.1f}%",
        f"- **Mean N content**: {metrics['mean_n_content']:.3f}%",
        f"- **Adapter contamination**: {metrics['adapter_rate']:.1f}%",
        "",
        "### Adapter Detection\n",
        "| Adapter | Hits | Rate |",
        "|---------|------|------|",
    ]
    for name, hits in metrics["adapter_hits"].items():
        rate = hits / max(metrics["n_reads"], 1) * 100
        body_lines.append(f"| {name} | {hits:,} | {rate:.2f}% |")
    body_lines.append("")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(
        "\n".join([header, "\n".join(body_lines), footer]), encoding="utf-8")

    summary = {k: v for k, v in metrics.items()
               if k not in ("per_base", "gc_fracs", "read_lengths", "all_quals")}
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, params)

    pd.DataFrame([summary]).to_csv(tables_dir / "qc_summary.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    (repro_dir / "commands.sh").write_text(
        f"#!/usr/bin/env bash\npython bulkrna_read_qc.py "
        f"--input {params.get('input', '<INPUT>')} "
        f"--output {params.get('output', '<OUTPUT>')}\n", encoding="utf-8")


def main() -> None:
    from skills._sdk.notebook import load_skill
    library = load_skill(SKILL_NAME)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=f"{SKILL_NAME} v{SKILL_VERSION}")
    ap.add_argument("--input", type=str, help="FASTQ file")
    ap.add_argument("--output", type=str, required=True)
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    output_dir = Path(args.output)

    if args.demo:
        output_dir.mkdir(parents=True, exist_ok=True)
        input_path = output_dir / "demo_reads.fastq"
        data = library.demo_data()
        with input_path.open('w') as stream:
            for i, (sequence, quality) in enumerate(data.itertuples(index=False, name=None)):
                stream.write(f'@READ_{i:06d}\n{sequence}\n+\n{quality}\n')
    else:
        if not args.input:
            ap.error("--input required (or use --demo)")
        input_path = Path(args.input)

    logger.info("Parsing FASTQ: %s", input_path)
    data = library.read_fastq(input_path)
    result = library.quality_control(data)
    metrics = library.run_info(result, keep=False)["metrics"]

    params = {"input": str(input_path), "output": str(output_dir)}
    generate_figures(output_dir, metrics)
    write_report(output_dir, metrics, params)
    logger.info("✓ FASTQ QC complete → %s", output_dir)


if __name__ == "__main__":
    main()
