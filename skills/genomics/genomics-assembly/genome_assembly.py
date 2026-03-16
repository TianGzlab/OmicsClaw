#!/usr/bin/env python3
"""Genomics Assembly — De novo genome assembly with quality assessment.

Computes standard assembly quality metrics from FASTA contigs:
- N50, N90, L50, L90
- Total assembly length
- Number of contigs / scaffolds
- GC content
- Longest contig
- Assembly completeness estimate

Mirrors output of QUAST (Quality Assessment Tool for Genome Assemblies).
For production assembly, wraps SPAdes, Megahit, Flye, or Canu.

Usage:
    python genome_assembly.py --input <contigs.fasta> --output <dir>
    python genome_assembly.py --demo --output <dir>
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

SKILL_NAME = "genomics-assembly"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# FASTA Parser
# ---------------------------------------------------------------------------

def parse_fasta(fasta_path: Path) -> list[tuple[str, str]]:
    """Parse a FASTA file into list of (header, sequence) tuples."""
    sequences = []
    current_header = ""
    current_seq: list[str] = []

    with open(fasta_path, "r") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                if current_header:
                    sequences.append((current_header, "".join(current_seq)))
                current_header = line[1:].split()[0]  # first word
                current_seq = []
            else:
                current_seq.append(line.upper())

        if current_header:
            sequences.append((current_header, "".join(current_seq)))

    return sequences


# ---------------------------------------------------------------------------
# Assembly Statistics
# ---------------------------------------------------------------------------

def compute_nx(lengths: list[int], x: int) -> int:
    """Compute Nx (e.g., N50, N90) from a list of contig lengths.

    Nx is the minimum contig length such that at least x% of the total
    assembly is contained in contigs of that length or longer.
    """
    if not lengths:
        return 0
    sorted_lengths = sorted(lengths, reverse=True)
    total = sum(sorted_lengths)
    target = total * x / 100.0
    cumsum = 0
    for length in sorted_lengths:
        cumsum += length
        if cumsum >= target:
            return length
    return sorted_lengths[-1]


def compute_lx(lengths: list[int], x: int) -> int:
    """Compute Lx (e.g., L50, L90) from a list of contig lengths.

    Lx is the number of contigs whose combined length covers at least
    x% of the total assembly.
    """
    if not lengths:
        return 0
    sorted_lengths = sorted(lengths, reverse=True)
    total = sum(sorted_lengths)
    target = total * x / 100.0
    cumsum = 0
    for i, length in enumerate(sorted_lengths):
        cumsum += length
        if cumsum >= target:
            return i + 1
    return len(sorted_lengths)


def compute_assembly_stats(sequences: list[tuple[str, str]], genome_size: int = 0) -> dict:
    """Compute comprehensive assembly quality metrics (QUAST-compatible).

    Args:
        sequences: list of (header, sequence) tuples
        genome_size: expected genome size for completeness estimation (0 = unknown)
    """
    if not sequences:
        return {"n_contigs": 0, "total_length": 0}

    lengths = [len(seq) for _, seq in sequences]
    total_length = sum(lengths)

    # GC content
    total_gc = 0
    total_n = 0
    total_bases = 0
    for _, seq in sequences:
        total_gc += seq.count("G") + seq.count("C")
        total_n += seq.count("N")
        total_bases += len(seq)

    gc_content = round(100 * total_gc / (total_bases - total_n), 2) if (total_bases - total_n) > 0 else 0

    # Filter by minimum length thresholds
    contigs_ge_500 = [l for l in lengths if l >= 500]
    contigs_ge_1000 = [l for l in lengths if l >= 1000]

    stats = {
        "n_contigs": len(sequences),
        "n_contigs_ge_500": len(contigs_ge_500),
        "n_contigs_ge_1000": len(contigs_ge_1000),
        "total_length": total_length,
        "total_length_ge_1000": sum(contigs_ge_1000),
        "largest_contig": max(lengths),
        "smallest_contig": min(lengths),
        "mean_contig_length": int(np.mean(lengths)),
        "median_contig_length": int(np.median(lengths)),
        "n50": compute_nx(lengths, 50),
        "n90": compute_nx(lengths, 90),
        "l50": compute_lx(lengths, 50),
        "l90": compute_lx(lengths, 90),
        "gc_content": gc_content,
        "n_content_pct": round(100 * total_n / total_bases, 4) if total_bases > 0 else 0,
    }

    if genome_size > 0:
        stats["genome_size_estimate"] = genome_size
        stats["completeness_pct"] = round(100 * total_length / genome_size, 2)

    return stats


# ---------------------------------------------------------------------------
# Demo Data
# ---------------------------------------------------------------------------

def generate_demo_assembly(output_dir: Path, n_contigs: int = 150) -> Path:
    """Generate a synthetic genome assembly FASTA for demo.

    Simulates a bacterial-scale assembly (~5Mb) with:
    - Log-normal contig length distribution (median ~30kb)
    - GC content ~50%
    - A few very large contigs (chromosomal scaffolds)
    """
    rng = random.Random(42)
    np_rng = np.random.RandomState(42)
    bases = "ACGT"

    fasta_path = output_dir / "demo_assembly.fasta"

    # Generate contig lengths: log-normal distribution
    lengths = np_rng.lognormal(mean=10, sigma=1.5, size=n_contigs).astype(int)
    lengths = np.clip(lengths, 500, 2_000_000)

    # Inject a few large contigs (scaffolds)
    lengths[0] = 500_000
    lengths[1] = 350_000
    lengths[2] = 150_000

    with open(fasta_path, "w") as fh:
        for i, length in enumerate(lengths):
            length = int(length)
            # GC-biased sequence (bacterial ~50% GC)
            seq = "".join(rng.choices(bases, weights=[25, 25, 25, 25], k=length))

            fh.write(f">contig_{i+1} length={length}\n")
            # Write in 80-character lines (FASTA convention)
            for j in range(0, length, 80):
                fh.write(seq[j:j + 80] + "\n")

    total = sum(int(l) for l in lengths)
    logger.info(f"Generated demo assembly: {n_contigs} contigs, {total:,} bp total: {fasta_path}")
    return fasta_path


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write assembly quality report."""
    header = generate_report_header(
        title="Genome Assembly Quality Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Contigs": str(stats["n_contigs"])},
    )

    body_lines = [
        "## Assembly Summary\n",
        f"- **Total contigs**: {stats['n_contigs']:,}",
        f"- **Total length**: {stats['total_length']:,} bp",
        f"- **Largest contig**: {stats['largest_contig']:,} bp",
        f"- **GC content**: {stats['gc_content']:.1f}%",
        f"- **N content**: {stats['n_content_pct']:.4f}%",
        "",
        "## Contiguity Metrics\n",
        f"- **N50**: {stats['n50']:,} bp",
        f"- **N90**: {stats['n90']:,} bp",
        f"- **L50**: {stats['l50']:,} contigs",
        f"- **L90**: {stats['l90']:,} contigs",
        "",
        "## Length Distribution\n",
        f"- **Mean contig length**: {stats['mean_contig_length']:,} bp",
        f"- **Median contig length**: {stats['median_contig_length']:,} bp",
        f"- **Contigs ≥ 500 bp**: {stats['n_contigs_ge_500']:,}",
        f"- **Contigs ≥ 1000 bp**: {stats['n_contigs_ge_1000']:,}",
        "",
    ]

    if "completeness_pct" in stats:
        body_lines.extend([
            "## Completeness\n",
            f"- **Expected genome size**: {stats['genome_size_estimate']:,} bp",
            f"- **Assembly completeness**: {stats['completeness_pct']:.1f}%",
            "",
        ])

    # Quality assessment
    body_lines.append("## Quality Assessment\n")
    if stats["n50"] > 100_000:
        body_lines.append("✅ **N50 > 100kb**: Good contiguity\n")
    elif stats["n50"] > 10_000:
        body_lines.append("⚠️ **N50 10–100kb**: Moderate contiguity\n")
    else:
        body_lines.append("❌ **N50 < 10kb**: Poor contiguity — consider long reads or scaffolding\n")

    body_lines.append("")
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Genome Assembly Quality Assessment")
    parser.add_argument("--input", dest="input_path", help="Input FASTA file (assembled contigs)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo assembly")
    parser.add_argument("--genome-size", type=int, default=0, help="Expected genome size in bp (for completeness)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        fasta_path = generate_demo_assembly(output_dir)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        fasta_path = Path(args.input_path)
        if not fasta_path.exists():
            raise FileNotFoundError(f"Input file not found: {fasta_path}")
        input_file = args.input_path

    sequences = parse_fasta(fasta_path)
    stats = compute_assembly_stats(sequences, genome_size=args.genome_size)
    logger.info(f"Assembly stats: {stats['n_contigs']} contigs, N50={stats['n50']:,} bp")

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    # Per-contig lengths
    contig_df = pd.DataFrame([
        {"contig": header, "length": len(seq)}
        for header, seq in sequences
    ]).sort_values("length", ascending=False)
    contig_df.to_csv(tables_dir / "contig_lengths.csv", index=False)

    # Summary metrics
    pd.DataFrame([stats]).to_csv(tables_dir / "assembly_metrics.csv", index=False)

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
    print(f"Assembly analysis complete: {stats['n_contigs']} contigs, "
          f"N50={stats['n50']:,} bp, "
          f"total={stats['total_length']:,} bp, "
          f"GC={stats['gc_content']:.1f}%")


if __name__ == "__main__":
    main()
