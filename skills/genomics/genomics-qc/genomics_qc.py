#!/usr/bin/env python3
"""Genomics QC — Quality control for FASTQ / BAM sequencing data.

Computes per-read quality metrics (Phred scores), GC/N content,
read-length distribution, per-base quality profiles, and adapter
contamination estimates. Mirrors outputs of FastQC / fastp.

Usage:
    python genomics_qc.py --input <file.fastq[.gz]> --output <dir>
    python genomics_qc.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import gzip
import logging
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "genomics-qc"
SKILL_VERSION = "0.3.0"

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


def qc_fastq(fastq_path: Path, max_reads: int = 500_000) -> dict:
    """Parse a FASTQ file and compute QC metrics.

    Metrics computed (matching FastQC/fastp conventions):
    - total_reads, total_bases
    - mean_quality (average Phred across all bases)
    - gc_content, n_content (as percentages)
    - per_base_quality: list of mean Phred per position (first 150 bp)
    - read_length_hist: Counter of read lengths
    - adapter_contamination: fraction of reads containing adapter prefix
    - q20_rate, q30_rate: fraction of bases >= Q20 / Q30
    """
    total_reads = 0
    total_bases = 0
    quality_sum = 0.0
    gc_count = 0
    n_count = 0
    base_count = 0

    max_pos = 300  # track per-base quality up to this length
    pos_qual_sum = np.zeros(max_pos, dtype=np.float64)
    pos_qual_cnt = np.zeros(max_pos, dtype=np.int64)

    length_counter: Counter = Counter()
    adapter_hits = 0

    q20_bases = 0
    q30_bases = 0

    with _open_fastq(fastq_path) as fh:
        while total_reads < max_reads:
            header = fh.readline()
            if not header:
                break
            seq = fh.readline().strip()
            _plus = fh.readline()
            qual_str = fh.readline().strip()

            if not seq or not qual_str:
                break

            total_reads += 1
            read_len = len(seq)
            total_bases += read_len
            length_counter[read_len] += 1

            # GC / N content
            seq_upper = seq.upper()
            gc_count += seq_upper.count("G") + seq_upper.count("C")
            n_count += seq_upper.count("N")
            base_count += read_len

            # Quality scores (Phred+33 encoding, standard for modern Illumina)
            quals = [ord(c) - 33 for c in qual_str]
            quality_sum += sum(quals)

            for i, q in enumerate(quals):
                if i < max_pos:
                    pos_qual_sum[i] += q
                    pos_qual_cnt[i] += 1
                if q >= 20:
                    q20_bases += 1
                if q >= 30:
                    q30_bases += 1

            # Adapter check (look for adapter prefix in last 20 bp of read)
            tail = seq_upper[-20:] if read_len >= 20 else seq_upper
            for adapter in ADAPTER_SEQS:
                if adapter[:8] in tail:
                    adapter_hits += 1
                    break

    if total_reads == 0:
        raise ValueError(f"No reads found in {fastq_path}")

    # Per-base quality (trim trailing zeros)
    valid_mask = pos_qual_cnt > 0
    per_base_quality = []
    for i in range(max_pos):
        if pos_qual_cnt[i] > 0:
            per_base_quality.append(round(pos_qual_sum[i] / pos_qual_cnt[i], 2))
        else:
            break

    return {
        "total_reads": total_reads,
        "total_bases": total_bases,
        "mean_quality": round(quality_sum / total_bases, 2) if total_bases else 0,
        "gc_content": round(100 * gc_count / base_count, 2) if base_count else 0,
        "n_content": round(100 * n_count / base_count, 4) if base_count else 0,
        "mean_length": round(total_bases / total_reads, 1),
        "q20_rate": round(100 * q20_bases / total_bases, 2) if total_bases else 0,
        "q30_rate": round(100 * q30_bases / total_bases, 2) if total_bases else 0,
        "adapter_contamination_pct": round(100 * adapter_hits / total_reads, 2),
        "per_base_quality": per_base_quality,
        "read_length_hist": dict(length_counter.most_common(20)),
    }


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

    result = qc_fastq(fastq_path, max_reads=args.max_reads)

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
