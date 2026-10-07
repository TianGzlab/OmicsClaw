"""Copy-ratio segmentation and summary calculations."""
from __future__ import annotations
import numpy as np
import pandas as pd
GAIN_THRESHOLD = 0.3
LOSS_THRESHOLD = -0.3
AMP_THRESHOLD = 1.0
DEEP_DEL_THRESHOLD = -1.0

def _t_statistic(data: np.ndarray, i: int, j: int) -> float:
    """Compute the CBS t-statistic for a candidate changepoint.

    The statistic measures the difference between the mean of the segment
    [i, j] and the rest of the data. Higher values indicate stronger
    evidence for a breakpoint.

    Ref: Venkatraman & Olshen (2007). "A faster circular binary
    segmentation algorithm for the analysis of array CGH data."
    """
    n = len(data)
    if j <= i or n < 3:
        return 0.0

    seg_mean = data[i:j].mean()
    rest_mean = np.concatenate([data[:i], data[j:]]).mean() if (i > 0 or j < n) else seg_mean
    seg_len = j - i

    # Avoid division by zero
    total_var = data.var()
    if total_var < 1e-10:
        return 0.0

    # t-statistic scaled by segment proportion
    t = abs(seg_mean - rest_mean) * np.sqrt(seg_len * (n - seg_len) / n) / np.sqrt(total_var)
    return float(t)

def cbs_segment(
    log2_ratios: np.ndarray,
    alpha: float = 0.01,
    min_segment_size: int = 3,
    max_iterations: int = 100,
) -> list[tuple[int, int, float]]:
    """Simplified CBS segmentation.

    Recursively splits data at the point that maximizes the t-statistic,
    stopping when no split exceeds the significance threshold.

    Args:
        log2_ratios: array of log2 copy-ratio values (ordered by genomic position)
        alpha: significance level (lower -> fewer breakpoints, more conservative)
        min_segment_size: minimum number of probes per segment
        max_iterations: maximum recursion depth

    Returns:
        List of (start_idx, end_idx, segment_mean) tuples
    """
    n = len(log2_ratios)
    if n < 2 * min_segment_size:
        return [(0, n, float(log2_ratios.mean()))]

    # Critical t-value increases with lower alpha (more conservative)
    # Approximate: for alpha=0.01 ~ 3.0, alpha=0.05 ~ 2.0
    t_crit = 2.0 + (-np.log10(alpha))

    segments: list[tuple[int, int, float]] = []

    def _recurse(start: int, end: int, depth: int = 0):
        if end - start < 2 * min_segment_size or depth > max_iterations:
            segments.append((start, end, float(log2_ratios[start:end].mean())))
            return

        data = log2_ratios[start:end]
        best_t = 0.0
        best_split = -1

        for k in range(min_segment_size, len(data) - min_segment_size):
            t = _t_statistic(data, 0, k)
            if t > best_t:
                best_t = t
                best_split = k

        if best_t > t_crit and best_split > 0:
            _recurse(start, start + best_split, depth + 1)
            _recurse(start + best_split, end, depth + 1)
        else:
            segments.append((start, end, float(data.mean())))

    _recurse(0, n)
    return segments

def call_cnv_from_segments(segments_df: pd.DataFrame) -> pd.DataFrame:
    """Classify CNV segments based on log2 ratio thresholds.

    Classification follows CNVkit conventions:
    - amplification: log2 > 1.0
    - gain: 0.3 < log2 <= 1.0
    - neutral: -0.3 <= log2 <= 0.3
    - loss: -1.0 <= log2 < -0.3
    - deep_deletion: log2 < -1.0
    """
    df = segments_df.copy()

    conditions = [
        df["log2_ratio"] > AMP_THRESHOLD,
        df["log2_ratio"] > GAIN_THRESHOLD,
        df["log2_ratio"] >= LOSS_THRESHOLD,
        df["log2_ratio"] >= DEEP_DEL_THRESHOLD,
    ]
    choices = ["amplification", "gain", "neutral", "loss"]
    df["cn_state"] = np.select(conditions, choices, default="deep_deletion")

    # Estimate integer copy number from log2 ratio (diploid baseline)
    # CN = 2 * 2^(log2_ratio)
    df["estimated_cn"] = np.round(2 * np.power(2, df["log2_ratio"]), 1)
    df["estimated_cn"] = df["estimated_cn"].clip(lower=0)

    return df

def run_cnv_analysis(df: pd.DataFrame, method: str = "cbs", alpha: float = 0.01) -> tuple[pd.DataFrame, dict]:
    """Segment bin-level log2 ratios already loaded by the caller.

    Steps:
    1. Group bin-level log2 ratios
    2. Segment per chromosome using CBS
    3. Classify CNV states
    4. Compute summary statistics
    """

    # Segment per chromosome
    segment_records = []
    for chrom in df["chrom"].unique():
        chrom_data = df[df["chrom"] == chrom].sort_values("start")
        log2_arr = chrom_data["log2_ratio"].values
        starts = chrom_data["start"].values
        ends = chrom_data["end"].values

        if method == "cbs":
            segments = cbs_segment(log2_arr, alpha=alpha)
        else:
            # Fallback: treat each bin as its own segment
            segments = [(i, i + 1, float(log2_arr[i])) for i in range(len(log2_arr))]

        for seg_start, seg_end, seg_mean in segments:
            segment_records.append({
                "chrom": chrom,
                "start": int(starts[seg_start]),
                "end": int(ends[min(seg_end - 1, len(ends) - 1)]),
                "n_bins": seg_end - seg_start,
                "log2_ratio": round(seg_mean, 4),
            })

    segments_df = pd.DataFrame(segment_records)

    # Call CNV states
    result_df = call_cnv_from_segments(segments_df)

    # Compute statistics
    gains = (result_df["cn_state"].isin(["gain", "amplification"])).sum()
    losses = (result_df["cn_state"].isin(["loss", "deep_deletion"])).sum()
    neutral = (result_df["cn_state"] == "neutral").sum()

    stats = {
        "n_segments": len(result_df),
        "n_gains": int(gains),
        "n_losses": int(losses),
        "n_neutral": int(neutral),
        "n_amplifications": int((result_df["cn_state"] == "amplification").sum()),
        "n_deep_deletions": int((result_df["cn_state"] == "deep_deletion").sum()),
        "method": method,
        "alpha": alpha,
        "gain_threshold": GAIN_THRESHOLD,
        "loss_threshold": LOSS_THRESHOLD,
        "genome_fraction_altered": round(
            (gains + losses) / len(result_df), 4
        ) if len(result_df) > 0 else 0,
    }
    return result_df, stats
