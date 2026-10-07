#!/usr/bin/env python3
"""Genomics qc: summarize existing local files.\n\nThe CLI owns demo generation, reports and file output. Its function library\ncontains the computations. No external analysis tool is started."""

from __future__ import annotations

import argparse
import gzip
import logging
import random
import sys
from pathlib import Path

import pandas as pd

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.report import (
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import write_result_json

logger = logging.getLogger(__name__)

SKILL_NAME = "genomics-qc"
SKILL_VERSION = "0.5.0"

# Common Illumina adapter prefix (TruSeq universal)
ADAPTER_SEQS = [
    "AGATCGGAAGAGC",
    "CTGTCTCTTATACACATCT",  # Nextera
]


# ---------------------------------------------------------------------------
# Core QC logic
# ---------------------------------------------------------------------------

def _phred_to_prob(q: int) -> float:
    """Convert Phred quality score to error probability."""
    return 10 ** (-q / 10.0)


def _open_fastq(path: Path):
    """Open plain or gzipped FASTQ."""
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt")
    return open(path, "r")


# ---------------------------------------------------------------------------
# Demo data generation
# ---------------------------------------------------------------------------

def _generate_demo_fastq(output_dir: Path, n_reads: int = 10000) -> Path:
    """Generate a minimal synthetic FASTQ file for demo purposes."""
    fastq_path = output_dir / "demo_reads.fastq"
    rng = random.Random(42)
    bases = "ACGT"

    with open(fastq_path, "w") as fh:
        for i in range(n_reads):
            read_len = rng.choice([100, 150])
            seq = "".join(rng.choice(bases) for _ in range(read_len))
            # Simulate quality: mostly Q30-Q40, with occasional dips
            quals = "".join(
                chr(33 + rng.randint(25, 40)) for _ in range(read_len)
            )
            fh.write(f"@read_{i}\n{seq}\n+\n{quals}\n")

    logger.info(f"Generated demo FASTQ with {n_reads} reads: {fastq_path}")
    return fastq_path


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write QC report in markdown format."""
    header = generate_report_header(
        title="Genomics Quality Control Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Reads": f"{summary['total_reads']:,}"},
    )

    body_lines = [
        "## Summary\n",
        f"- **Total reads**: {summary['total_reads']:,}",
        f"- **Total bases**: {summary['total_bases']:,}",
        f"- **Mean quality (Phred)**: {summary['mean_quality']:.1f}",
        f"- **GC content**: {summary['gc_content']:.1f}%",
        f"- **N content**: {summary['n_content']:.4f}%",
        f"- **Mean read length**: {summary['mean_length']} bp",
        f"- **Q20 rate**: {summary['q20_rate']:.1f}%",
        f"- **Q30 rate**: {summary['q30_rate']:.1f}%",
        f"- **Adapter contamination**: {summary['adapter_contamination_pct']:.1f}%",
        "",
        "## Quality Assessment\n",
    ]

    # Simple quality verdict
    if summary["mean_quality"] >= 30:
        body_lines.append("✅ **Overall quality**: PASS (mean Q ≥ 30)\n")
    elif summary["mean_quality"] >= 20:
        body_lines.append("⚠️ **Overall quality**: WARN (20 ≤ mean Q < 30)\n")
    else:
        body_lines.append("❌ **Overall quality**: FAIL (mean Q < 20)\n")

    if summary["adapter_contamination_pct"] > 5:
        body_lines.append("⚠️ **Adapter contamination** >5% — consider trimming with fastp/Trimmomatic\n")

    body_lines.append("")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python genomics_qc.py --input <fastq> --output {output_dir}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Genomics QC — FASTQ quality control")
    parser.add_argument("--input", dest="input_path", help="Input FASTQ file (.fastq or .fastq.gz)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    parser.add_argument("--max-reads", type=int, default=500_000, help="Max reads to process (default: 500000)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        fastq_path = _generate_demo_fastq(output_dir)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        fastq_path = Path(args.input_path)
        if not fastq_path.exists():
            raise FileNotFoundError(f"Input file not found: {fastq_path}")
        input_file = args.input_path

    from skills._sdk.notebook import load_skill
    api = load_skill(SKILL_NAME)
    table = api.analyze(api.read_records(fastq_path, max_reads=args.max_reads), max_reads=args.max_reads)
    result = api.run_info(table, keep=False)["summary"]

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    # Main metrics table
    metrics_row = {k: v for k, v in result.items() if k not in ("per_base_quality", "read_length_hist")}
    pd.DataFrame([metrics_row]).to_csv(tables_dir / "qc_metrics.csv", index=False)

    # Per-base quality table
    if result["per_base_quality"]:
        pd.DataFrame({
            "position": list(range(1, len(result["per_base_quality"]) + 1)),
            "mean_quality": result["per_base_quality"],
        }).to_csv(tables_dir / "per_base_quality.csv", index=False)

    # Read length distribution
    if result["read_length_hist"]:
        hist_df = pd.DataFrame(
            sorted(result["read_length_hist"].items()),
            columns=["read_length", "count"],
        )
        hist_df.to_csv(tables_dir / "read_length_distribution.csv", index=False)

    params = {"max_reads": args.max_reads}
    write_report(output_dir, result, input_file, params)
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=metrics_row,
        data={"params": params},
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"QC complete: {result['total_reads']:,} reads, mean Q{result['mean_quality']:.1f}")


if __name__ == "__main__":
    main()
