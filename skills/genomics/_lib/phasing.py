"""Parsing and calculations for phasing."""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np


def compute_n50(lengths: list[int]) -> int:
    """Compute N50 from a list of lengths.

    N50 is the smallest length L such that the sum of all lengths >= L
    covers at least 50% of the total sum.
    """
    if not lengths:
        return 0
    sorted_lengths = sorted(lengths, reverse=True)
    total = sum(sorted_lengths)
    cumsum = 0
    for length in sorted_lengths:
        cumsum += length
        if cumsum >= total / 2:
            return length
    return sorted_lengths[-1]

def parse_phased_vcf(vcf_path: Path) -> tuple[list[dict], dict[str, list[dict]]]:
    """Parse a phased VCF and extract phase block information.

    Detects phase blocks from the PS (Phase Set) FORMAT field.
    Heterozygous variants with the same PS value on the same chromosome
    belong to the same phase block.

    Also handles pipe-delimited genotypes (0|1, 1|0) as indicators
    of phased genotypes (vs. slash-delimited 0/1 for unphased).
    """
    variants = []
    phase_blocks: dict[str, list[dict]] = defaultdict(list)

    with open(vcf_path, "r") as fh:
        format_idx = -1
        for line in fh:
            if line.startswith("##"):
                continue
            if line.startswith("#CHROM"):
                header = line.strip().split("\t")
                if "FORMAT" in header:
                    format_idx = header.index("FORMAT")
                continue

            fields = line.strip().split("\t")
            if len(fields) < 10:
                continue

            chrom = fields[0]
            pos = int(fields[1])
            ref = fields[3]
            alt = fields[4]

            # Parse FORMAT and sample
            fmt_keys = fields[format_idx].split(":") if format_idx >= 0 else []
            sample_vals = fields[format_idx + 1].split(":") if format_idx >= 0 and len(fields) > format_idx + 1 else []

            fmt_dict = dict(zip(fmt_keys, sample_vals))
            gt = fmt_dict.get("GT", ".")
            ps = fmt_dict.get("PS", ".")

            # Determine if phased (pipe delimiter = phased)
            is_phased = "|" in gt
            is_het = gt in ("0|1", "1|0", "0/1", "1/0")

            variant = {
                "chrom": chrom,
                "pos": pos,
                "ref": ref,
                "alt": alt,
                "gt": gt,
                "is_phased": is_phased,
                "is_het": is_het,
                "phase_set": ps if ps != "." else str(pos),
            }
            variants.append(variant)

            if is_phased and is_het:
                block_key = f"{chrom}:{variant['phase_set']}"
                phase_blocks[block_key].append(variant)

    return variants, dict(phase_blocks)

def compute_phasing_stats(
    variants: list[dict],
    phase_blocks: dict[str, list[dict]],
) -> dict:
    """Compute phasing quality metrics.

    Metrics:
    - Phase block N50 (in bp and in variants)
    - Longest phase block
    - Fraction of heterozygous variants phased
    - Number of phase blocks
    """
    het_variants = [v for v in variants if v["is_het"]]
    phased_het = [v for v in het_variants if v["is_phased"]]

    # Phase block lengths (in bp)
    block_lengths_bp = []
    block_lengths_variants = []
    for block_key, block_vars in phase_blocks.items():
        if len(block_vars) < 2:
            continue
        positions = sorted(v["pos"] for v in block_vars)
        bp_len = positions[-1] - positions[0]
        block_lengths_bp.append(bp_len)
        block_lengths_variants.append(len(block_vars))

    # N50 calculations
    n50_bp = compute_n50(block_lengths_bp)
    n50_variants = compute_n50(block_lengths_variants)

    stats = {
        "n_total_variants": len(variants),
        "n_het_variants": len(het_variants),
        "n_phased_het": len(phased_het),
        "phased_fraction": round(len(phased_het) / max(1, len(het_variants)), 4),
        "n_phase_blocks": len(block_lengths_bp),
        "phase_block_n50_bp": n50_bp,
        "phase_block_n50_variants": n50_variants,
        "longest_block_bp": max(block_lengths_bp) if block_lengths_bp else 0,
        "longest_block_variants": max(block_lengths_variants) if block_lengths_variants else 0,
        "mean_block_length_bp": int(np.mean(block_lengths_bp)) if block_lengths_bp else 0,
        "median_block_length_bp": int(np.median(block_lengths_bp)) if block_lengths_bp else 0,
    }
    return stats


def group_blocks(data):
    blocks = {}
    for variant in data.to_dict("records"):
        if variant["is_phased"] and variant["is_het"]:
            blocks.setdefault(f'{variant["chrom"]}:{variant["phase_set"]}', []).append(variant)
    return blocks
