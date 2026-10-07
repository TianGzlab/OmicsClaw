"""Bulk differential-expression backends shared by the CLI and library."""
import logging
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
logger = logging.getLogger(__name__)
SUPPORTED_METHODS = ("deseq2", "ttest")

def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Manual Benjamini-Hochberg FDR correction with NaN handling."""
    pv = np.asarray(pvalues, dtype=float)
    n = len(pv)
    if n == 0:
        return pv
    # Handle NaN: track non-NaN positions
    nan_mask = np.isnan(pv)
    non_nan_indices = np.where(~nan_mask)[0]
    pv_clean = pv[non_nan_indices]
    m = len(pv_clean)
    if m == 0:
        return pv
    order = np.argsort(pv_clean)
    sorted_p = pv_clean[order]
    adjusted = np.empty(m, dtype=float)
    adjusted[-1] = sorted_p[-1]
    for i in range(m - 2, -1, -1):
        rank = i + 1
        adjusted[i] = min(sorted_p[i] * m / rank, adjusted[i + 1])
    adjusted = np.clip(adjusted, 0.0, 1.0)
    result_clean = np.empty(m, dtype=float)
    result_clean[order] = adjusted
    result = np.full(n, np.nan)
    result[non_nan_indices] = result_clean
    return result

def _run_deseq2_r(
    counts: pd.DataFrame,
    gene_col: str,
    control_prefix: str,
    treat_prefix: str,
) -> pd.DataFrame:
    """Run real DESeq2 in R via subprocess. Raises ImportError if R/DESeq2 unavailable."""
    import tempfile
    from skills._sdk.deps import validate_r_environment
    from skills._sdk.r_script_runner import RScriptRunner
    from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR

    validate_r_environment(required_r_packages=["DESeq2"])

    scripts_dir = _SDK_R_SCRIPTS_DIR
    runner = RScriptRunner(scripts_dir=scripts_dir)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_bulkde_") as tmpdir:
        tmpdir = Path(tmpdir)
        # Write counts with gene names as row index
        counts_for_r = counts.set_index(gene_col)
        counts_for_r.to_csv(tmpdir / "counts.csv")

        output_dir = tmpdir / "output"
        output_dir.mkdir()

        runner.run_script(
            "bulkrna_deseq2.R",
            args=[str(tmpdir / "counts.csv"), str(output_dir),
                  control_prefix, treat_prefix],
            expected_outputs=["deseq2_results.csv"],
            output_dir=output_dir,
        )

        de_df = pd.read_csv(output_dir / "deseq2_results.csv")

    # Standardize column names
    rename_map = {}
    for col in de_df.columns:
        lc = col.lower()
        if lc == "basemean":
            rename_map[col] = "baseMean"
        elif lc in ("log2foldchange", "log2_fold_change"):
            rename_map[col] = "log2FoldChange"
        elif lc == "pvalue":
            rename_map[col] = "pvalue"
        elif lc == "padj":
            rename_map[col] = "padj"
    if rename_map:
        de_df = de_df.rename(columns=rename_map)

    return de_df

def _run_ttest(counts: pd.DataFrame, ctrl_cols: list[str], treat_cols: list[str]) -> pd.DataFrame:
    """Welch's t-test per gene with BH FDR correction.
    *counts*: genes-as-rows DataFrame; first column is gene name.

    Produces output columns consistent with DESeq2: gene, baseMean,
    log2FoldChange, lfcSE, stat, pvalue, padj.
    """
    gene_col = counts.columns[0]
    records: list[dict] = []
    for _, row in counts.iterrows():
        ctrl_vals = row[ctrl_cols].values.astype(float)
        treat_vals = row[treat_cols].values.astype(float)
        mean_ctrl = float(np.mean(ctrl_vals))
        mean_treat = float(np.mean(treat_vals))
        base_mean = (mean_ctrl + mean_treat) / 2.0
        log2fc = np.log2(mean_treat + 1) - np.log2(mean_ctrl + 1)

        # Standard error of log2FC (delta method approximation)
        se_ctrl = float(np.std(ctrl_vals, ddof=1)) / (mean_ctrl + 1) / np.log(2) if len(ctrl_vals) > 1 else 0.0
        se_treat = float(np.std(treat_vals, ddof=1)) / (mean_treat + 1) / np.log(2) if len(treat_vals) > 1 else 0.0
        lfc_se = float(np.sqrt(se_ctrl**2 / max(len(ctrl_vals), 1) + se_treat**2 / max(len(treat_vals), 1)))

        if np.std(ctrl_vals) == 0 and np.std(treat_vals) == 0:
            pval = 1.0
            t_stat = 0.0
        else:
            t_stat_val, pval = stats.ttest_ind(ctrl_vals, treat_vals, equal_var=False)
            t_stat = float(t_stat_val) if not np.isnan(t_stat_val) else 0.0
            pval = float(pval) if not np.isnan(pval) else 1.0

        records.append({
            "gene": row[gene_col],
            "baseMean": round(base_mean, 4),
            "log2FoldChange": round(float(log2fc), 6),
            "lfcSE": round(lfc_se, 6),
            "stat": round(t_stat, 6),
            "pvalue": pval,
        })
    result = pd.DataFrame(records)
    result["padj"] = _benjamini_hochberg(result["pvalue"].values)
    return result.sort_values("pvalue").reset_index(drop=True)

def core_analysis(
    counts: pd.DataFrame,
    *,
    method: str = "deseq2",
    control_prefix: str = "ctrl",
    treat_prefix: str = "treat",
    padj_cutoff: float = 0.05,
    lfc_cutoff: float = 1.0,
    min_count: int = 10,
) -> dict:
    """Run DE analysis and return a summary dict."""
    gene_col = counts.columns[0]
    sample_cols = [c for c in counts.columns if c != gene_col]
    ctrl_cols = [c for c in sample_cols if c.startswith(control_prefix)]
    treat_cols = [c for c in sample_cols if c.startswith(treat_prefix)]
    if not ctrl_cols:
        raise ValueError(f"No columns matching control prefix '{control_prefix}'")
    if not treat_cols:
        raise ValueError(f"No columns matching treatment prefix '{treat_prefix}'")

    # Design validation (from Biomni basic_workflow.R best practices)
    n_ctrl, n_treat = len(ctrl_cols), len(treat_cols)
    if n_ctrl < 2 or n_treat < 2:
        logger.warning(
            "Insufficient replicates: %d control, %d treatment. "
            "DESeq2 requires >= 2 replicates per condition (>= 3 recommended).",
            n_ctrl, n_treat,
        )
    elif n_ctrl < 3 or n_treat < 3:
        logger.info(
            "Low replication: %d control, %d treatment. "
            "Consider >= 3 replicates per condition for reliable dispersion estimation.",
            n_ctrl, n_treat,
        )
    else:
        logger.info("Design: %d control, %d treatment samples", n_ctrl, n_treat)

    # Gene pre-filtering: remove low-count genes (from Biomni basic_workflow.R)
    n_genes_raw = len(counts)
    numeric_cols = ctrl_cols + treat_cols
    row_sums = counts[numeric_cols].sum(axis=1)
    counts_filtered = counts[row_sums >= min_count].copy()
    n_genes_filtered = len(counts_filtered)
    n_removed = n_genes_raw - n_genes_filtered
    if n_removed > 0:
        logger.info(
            "Pre-filtered genes: %d → %d (removed %d with rowSum < %d)",
            n_genes_raw, n_genes_filtered, n_removed, min_count,
        )
    counts = counts_filtered
    method_used = method
    fallback = {}
    if method == "deseq2":
        try:
            de_df = _run_deseq2_r(counts, gene_col, control_prefix, treat_prefix)
            method_used = "deseq2"
            logger.info("R DESeq2 completed successfully.")
        except ImportError:
            raise
        except Exception as exc:
            logger.warning("R DESeq2 failed (%s); falling back to t-test.", exc)
            de_df = _run_ttest(counts, ctrl_cols, treat_cols)
            method_used = "ttest"
            fallback = dict(requested_method=method, executed_method='ttest', fallback_reason=str(exc))
            warnings.warn(f'R DESeq2 failed; using Welch t-test: {exc}', RuntimeWarning, stacklevel=2)
    elif method == "ttest":
        de_df = _run_ttest(counts, ctrl_cols, treat_cols)
        method_used = "ttest"
    else:
        raise ValueError(f"Unknown method '{method}'. Choose from {SUPPORTED_METHODS}")

    sig = de_df.dropna(subset=["padj"])
    sig = sig[(sig["padj"] < padj_cutoff) & (sig["log2FoldChange"].abs() > lfc_cutoff)]
    n_up = int((sig["log2FoldChange"] > 0).sum())
    n_down = int((sig["log2FoldChange"] < 0).sum())
    n_tested = int(de_df["padj"].notna().sum())
    frac_sig = len(sig) / max(n_tested, 1)

    return {
        'requested_method': method,
        'executed_method': method_used,
        'fallback_reason': None,
        **fallback,
        "n_genes": len(de_df), "n_genes_raw": n_genes_raw,
        "n_genes_filtered": n_genes_filtered, "n_genes_prefiltered": n_removed,
        "n_samples": len(ctrl_cols) + len(treat_cols),
        "n_ctrl": len(ctrl_cols), "n_treat": len(treat_cols),
        "method_used": method_used, "n_de_genes": len(sig),
        "n_up": n_up, "n_down": n_down,
        "n_tested": n_tested, "frac_significant": round(frac_sig, 4),
        "padj_cutoff": padj_cutoff, "lfc_cutoff": lfc_cutoff,
        "lfc_note": (
            "R DESeq2 uses apeglm or ashr shrinkage when installed; otherwise raw estimates."
        ) if method_used == 'deseq2' else (
            "LFCs are unshrunk (suitable for hypothesis testing). "
            "For visualization/ranking, consider apeglm or ashr shrinkage."
        ),
        "de_df": de_df,
    }
