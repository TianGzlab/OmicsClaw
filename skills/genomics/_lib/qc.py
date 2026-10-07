"""Parsing and calculations for qc."""
from __future__ import annotations
from collections import Counter
import numpy as np
import pandas as pd

ADAPTER_SEQS = [
    "AGATCGGAAGAGC",
    "CTGTCTCTTATACACATCT",  # Nextera
]

def qc_records(data: pd.DataFrame, max_reads: int = 500_000) -> dict:
    """Compute QC metrics from sequence and quality columns.

    Metrics computed (matching FastQC/fastp conventions):
    - total_reads, total_bases
    - mean_quality (average Phred across all bases)
    - gc_content, n_content (as percentages)
    - per_base_quality: list of mean Phred per position (first 300 bp)
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

    for record in data.head(max_reads).itertuples(index=False):
        seq, qual_str = record.sequence, record.quality
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
        raise ValueError("No reads found")

    # Per-base quality (trim trailing zeros)
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
