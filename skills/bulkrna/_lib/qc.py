"""Count-matrix quality statistics shared by the CLI and function library."""
import numpy as np
import pandas as pd

def _detect_sample_groups(sample_names: list[str]) -> dict[str, str]:
    """Auto-detect sample groups from common prefix patterns.

    Returns a mapping of sample_name -> group_label.
    """
    # Try common prefix patterns
    groups: dict[str, str] = {}
    for name in sample_names:
        parts = name.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            groups[name] = parts[0]
        else:
            groups[name] = name
    return groups


def core_analysis(counts: pd.DataFrame) -> dict:
    """Compute library size QC, gene detection rates, sample correlation,
    and outlier flagging.

    Parameters
    ----------
    counts : DataFrame
        Gene-by-sample count matrix (genes as rows, samples as columns).

    Returns
    -------
    dict with summary statistics.
    """
    n_genes, n_samples = counts.shape
    sample_names = list(counts.columns)

    # Library sizes
    lib_sizes = counts.sum(axis=0)
    library_sizes = {s: int(v) for s, v in lib_sizes.items()}
    mean_lib = float(lib_sizes.mean())
    median_lib = float(lib_sizes.median())
    cv_lib = float(lib_sizes.std() / lib_sizes.mean()) if mean_lib > 0 else 0.0

    # Gene detection: how many samples detect each gene (count > 0)
    gene_detection = (counts > 0).sum(axis=1)
    n_zero_genes = int((gene_detection == 0).sum())

    # CPM (Counts Per Million)
    cpm = counts.div(lib_sizes, axis=1) * 1e6

    # Per-sample stats
    per_sample_stats = {}
    for sample in sample_names:
        total = int(counts[sample].sum())
        n_detected = int((counts[sample] > 0).sum())
        pct_detected = round(100.0 * n_detected / n_genes, 2) if n_genes > 0 else 0.0
        per_sample_stats[sample] = {
            "total_counts": total,
            "n_detected_genes": n_detected,
            "pct_detected": pct_detected,
        }

    # Sample correlation matrix (Pearson on log-CPM)
    log_cpm = np.log2(cpm + 1)
    corr_matrix = log_cpm.astype(float).corr(method="pearson")
    corr_list = corr_matrix.values.tolist()

    # Outlier detection: flag samples with mean correlation < median - 2*MAD
    mean_corrs = corr_matrix.mean(axis=0)
    median_corr = float(mean_corrs.median())
    mad_corr = float((mean_corrs - median_corr).abs().median()) * 1.4826
    outlier_threshold = median_corr - 2.0 * mad_corr
    outlier_samples = [s for s in sample_names
                       if float(mean_corrs[s]) < outlier_threshold]

    # Auto-detect groups
    sample_groups = _detect_sample_groups(sample_names)

    summary = {
        "n_genes": n_genes,
        "n_samples": n_samples,
        "sample_names": sample_names,
        "sample_groups": sample_groups,
        "library_sizes": library_sizes,
        "mean_library_size": round(mean_lib, 1),
        "median_library_size": round(median_lib, 1),
        "cv_library_size": round(cv_lib, 4),
        "gene_detection": {g: int(v) for g, v in gene_detection.items()},
        "n_zero_genes": n_zero_genes,
        "per_sample_stats": per_sample_stats,
        "sample_correlation_matrix": corr_list,
        "outlier_samples": outlier_samples,
        "cpm": cpm,
    }
    return summary
