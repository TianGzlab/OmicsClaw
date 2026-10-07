"""Parsing and calculations for alignment."""
from __future__ import annotations
import numpy as np
import pandas as pd

_FLAG_PAIRED       = 0x1
_FLAG_PROPER_PAIR  = 0x2
_FLAG_UNMAPPED     = 0x4
_FLAG_SECONDARY    = 0x100
_FLAG_SUPPLEMENTARY = 0x800
_FLAG_DUPLICATE    = 0x400

def alignment_stats(data: pd.DataFrame) -> dict:
    """Compute flag-based metrics from parsed SAM fields.

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

    for record in data.itertuples(index=False):
        total += 1
        flag = int(record.flag)
        mapq = int(record.mapq)
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
                tlen = abs(int(record.tlen))
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
