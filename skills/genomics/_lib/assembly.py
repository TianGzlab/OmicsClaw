"""Parsing and calculations for assembly."""
from __future__ import annotations
from pathlib import Path
import numpy as np


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
