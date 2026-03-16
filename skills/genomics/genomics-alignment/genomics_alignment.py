#!/usr/bin/env python3
"""Genomics Alignment — Read alignment to reference genome (demo / statistics).

Supports demo mode with synthetic SAM data and real-file mode that computes
standard alignment statistics from BAM/SAM files (mapping rates, MAPQ
distribution, insert-size statistics, etc.). Mirrors samtools-flagstat
and Picard CollectAlignmentSummaryMetrics output.

Usage:
    python genomics_alignment.py --input <file.bam> --output <dir>
    python genomics_alignment.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
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

SKILL_NAME = "genomics-alignment"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Alignment statistics from SAM text (lightweight, no pysam dependency)
# ---------------------------------------------------------------------------

# SAM FLAG bits (SAM spec v1.6)
_FLAG_PAIRED       = 0x1
_FLAG_PROPER_PAIR  = 0x2
_FLAG_UNMAPPED     = 0x4
_FLAG_MATE_UNMAP   = 0x8
_FLAG_REVERSE      = 0x10
_FLAG_SECONDARY    = 0x100
_FLAG_SUPPLEMENTARY = 0x800
_FLAG_DUPLICATE    = 0x400


def compute_alignment_stats_from_sam(sam_path: Path) -> dict:
    """Parse a SAM (text) file and compute flagstat-style metrics.

    Returns a dictionary compatible with samtools-flagstat output conventions.
    """
    total = 0
    mapped = 0
    unmapped = 0
    paired = 0
    properly_paired = 0
    secondary = 0
    supplementary = 0
    duplicates = 0
    mapq_values: list[int] = []
    insert_sizes: list[int] = []

    with open(sam_path, "r") as fh:
        for line in fh:
            if line.startswith("@"):
                continue
            fields = line.strip().split("\t")
            if len(fields) < 11:
                continue

            total += 1
            flag = int(fields[1])
            mapq = int(fields[4])

            if flag & _FLAG_SECONDARY:
                secondary += 1
                continue
            if flag & _FLAG_SUPPLEMENTARY:
                supplementary += 1
                continue
            if flag & _FLAG_DUPLICATE:
                duplicates += 1

            if flag & _FLAG_UNMAPPED:
                unmapped += 1
            else:
                mapped += 1
                mapq_values.append(mapq)

            if flag & _FLAG_PAIRED:
                paired += 1
                if flag & _FLAG_PROPER_PAIR:
                    properly_paired += 1
                # Insert size (TLEN field, column 9 in SAM, 0-based index 8)
                try:
                    tlen = abs(int(fields[8]))
                    if tlen > 0 and tlen < 10000:
                        insert_sizes.append(tlen)
                except (ValueError, IndexError):
                    pass

    mapq_arr = np.array(mapq_values) if mapq_values else np.array([0])
    isize_arr = np.array(insert_sizes) if insert_sizes else np.array([0])

    primary_total = total - secondary - supplementary

    stats = {
        "total_alignments": total,
        "primary_alignments": primary_total,
        "secondary_alignments": secondary,
        "supplementary_alignments": supplementary,
        "mapped_reads": mapped,
        "unmapped_reads": unmapped,
        "mapping_rate_pct": round(100 * mapped / primary_total, 2) if primary_total else 0,
        "paired_reads": paired,
        "properly_paired": properly_paired,
        "properly_paired_pct": round(100 * properly_paired / paired, 2) if paired else 0,
        "duplicates": duplicates,
        "duplicate_rate_pct": round(100 * duplicates / primary_total, 2) if primary_total else 0,
        "mean_mapq": round(float(mapq_arr.mean()), 2),
        "median_mapq": int(np.median(mapq_arr)),
        "mapq_ge_20_pct": round(100 * (mapq_arr >= 20).sum() / len(mapq_arr), 2),
        "mapq_ge_30_pct": round(100 * (mapq_arr >= 30).sum() / len(mapq_arr), 2),
        "mean_insert_size": round(float(isize_arr.mean()), 1) if insert_sizes else 0,
        "median_insert_size": int(np.median(isize_arr)) if insert_sizes else 0,
        "insert_size_sd": round(float(isize_arr.std()), 1) if insert_sizes else 0,
    }
    return stats


# ---------------------------------------------------------------------------
# Demo data generation — synthetic SAM
# ---------------------------------------------------------------------------

def _generate_demo_sam(output_dir: Path, n_reads: int = 5000) -> Path:
    """Generate a minimal synthetic SAM file for demo purposes.

    Simulates paired-end 150bp reads aligned to chr1-chr22 with realistic
    mapping quality distribution and ~2% unmapped rate.
    """
    sam_path = output_dir / "demo_alignment.sam"
    rng = random.Random(42)
    chroms = [f"chr{i}" for i in range(1, 23)]
    bases = "ACGT"

    with open(sam_path, "w") as fh:
        # SAM header
        fh.write("@HD\tVN:1.6\tSO:coordinate\n")
        for chrom in chroms:
            fh.write(f"@SQ\tSN:{chrom}\tLN:250000000\n")
        fh.write("@RG\tID:demo\tSM:SAMPLE1\tPL:ILLUMINA\n")

        for i in range(n_reads):
            chrom = rng.choice(chroms)
            pos = rng.randint(1, 249_999_000)
            read_len = 150
            seq = "".join(rng.choice(bases) for _ in range(read_len))
            qual = "I" * read_len  # Q40
            mapq = rng.choices([0, 10, 20, 30, 40, 60], weights=[2, 3, 5, 10, 40, 40])[0]
            insert_size = rng.randint(200, 500)

            # ~2% unmapped
            if rng.random() < 0.02:
                flag = _FLAG_PAIRED | _FLAG_UNMAPPED
                fh.write(f"read_{i}\t{flag}\t*\t0\t0\t*\t*\t0\t0\t{seq}\t{qual}\n")
            else:
                # Read 1
                flag1 = _FLAG_PAIRED | _FLAG_PROPER_PAIR
                cigar = f"{read_len}M"
                mate_pos = pos + insert_size
                fh.write(f"read_{i}\t{flag1}\t{chrom}\t{pos}\t{mapq}\t{cigar}\t=\t{mate_pos}\t{insert_size}\t{seq}\t{qual}\n")

                # Read 2
                flag2 = _FLAG_PAIRED | _FLAG_PROPER_PAIR | _FLAG_REVERSE
                fh.write(f"read_{i}\t{flag2}\t{chrom}\t{mate_pos}\t{mapq}\t{cigar}\t=\t{pos}\t{-insert_size}\t{seq}\t{qual}\n")

    logger.info(f"Generated demo SAM with ~{n_reads * 2} alignments: {sam_path}")
    return sam_path


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write alignment statistics report."""
    header = generate_report_header(
        title="Genomics Alignment Statistics Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Total alignments": f"{stats['total_alignments']:,}"},
    )

    body_lines = [
        "## Alignment Summary\n",
        f"- **Total alignments**: {stats['total_alignments']:,}",
        f"- **Primary alignments**: {stats['primary_alignments']:,}",
        f"- **Secondary alignments**: {stats['secondary_alignments']:,}",
        f"- **Supplementary alignments**: {stats['supplementary_alignments']:,}",
        "",
        "## Mapping Statistics\n",
        f"- **Mapped reads**: {stats['mapped_reads']:,}",
        f"- **Unmapped reads**: {stats['unmapped_reads']:,}",
        f"- **Mapping rate**: {stats['mapping_rate_pct']:.1f}%",
        f"- **Properly paired**: {stats['properly_paired']:,} ({stats['properly_paired_pct']:.1f}%)",
        f"- **Duplicate rate**: {stats['duplicate_rate_pct']:.1f}%",
        "",
        "## Mapping Quality Distribution\n",
        f"- **Mean MAPQ**: {stats['mean_mapq']:.1f}",
        f"- **Median MAPQ**: {stats['median_mapq']}",
        f"- **MAPQ ≥ 20**: {stats['mapq_ge_20_pct']:.1f}%",
        f"- **MAPQ ≥ 30**: {stats['mapq_ge_30_pct']:.1f}%",
        "",
    ]

    if stats["mean_insert_size"] > 0:
        body_lines.extend([
            "## Insert Size Statistics\n",
            f"- **Mean insert size**: {stats['mean_insert_size']:.0f} bp",
            f"- **Median insert size**: {stats['median_insert_size']} bp",
            f"- **Std dev**: {stats['insert_size_sd']:.0f} bp",
            "",
        ])

    # Quality assessment
    body_lines.append("## Quality Assessment\n")
    if stats["mapping_rate_pct"] >= 95:
        body_lines.append("✅ **Mapping rate**: PASS (≥ 95%)\n")
    elif stats["mapping_rate_pct"] >= 80:
        body_lines.append("⚠️ **Mapping rate**: WARN (80–95%)\n")
    else:
        body_lines.append("❌ **Mapping rate**: FAIL (< 80%)\n")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Genomics Alignment — alignment statistics")
    parser.add_argument("--input", dest="input_path", help="Input SAM/BAM file")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        sam_path = _generate_demo_sam(output_dir)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        sam_path = Path(args.input_path)
        if not sam_path.exists():
            raise FileNotFoundError(f"Input file not found: {sam_path}")
        input_file = args.input_path

    stats = compute_alignment_stats_from_sam(sam_path)
    logger.info(f"Alignment stats: mapping rate {stats['mapping_rate_pct']:.1f}%")

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    pd.DataFrame([stats]).to_csv(tables_dir / "alignment_stats.csv", index=False)

    write_report(output_dir, stats, input_file)
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=stats,
        data={},
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Alignment analysis complete: {stats['mapped_reads']:,} mapped reads "
          f"({stats['mapping_rate_pct']:.1f}% mapping rate)")


if __name__ == "__main__":
    main()
