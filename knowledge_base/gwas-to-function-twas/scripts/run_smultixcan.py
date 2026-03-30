"""
S-MultiXcan Cross-Tissue Analysis Wrapper

This module provides a Python wrapper for running S-MultiXcan to identify genes
with consistent expression-trait associations across multiple tissues.
"""

import pandas as pd
import subprocess
from pathlib import Path


def run_smultixcan(gwas_sumstats, weights_dir, output_prefix="results/smultixcan/cross_tissue"):
    """
    Run S-MultiXcan cross-tissue meta-analysis.

    S-MultiXcan aggregates expression-trait associations across all GTEx tissues
    to identify genes with consistent effects.

    Parameters
    ----------
    gwas_sumstats : str
        Path to GWAS summary statistics
    weights_dir : str
        Directory containing GTEx v8 expression weights
    output_prefix : str
        Output file prefix

    Returns
    -------
    pandas.DataFrame
        S-MultiXcan results with cross-tissue P-values
    """
    output_path = Path(output_prefix).parent
    output_path.mkdir(parents=True, exist_ok=True)

    print("Running S-MultiXcan cross-tissue analysis...")

    # S-MultiXcan command
    cmd = [
        'python',
        '-m', 'metaxcan.SMulTiXcan',
        '--models_folder', weights_dir,
        '--models_name_pattern', 'gtex_v8_mashr_(.*).db',
        '--snp_covariance', f'{weights_dir}/gtex_v8_expression_covariance.txt.gz',
        '--gwas_file', gwas_sumstats,
        '--snp_column', 'SNP',
        '--effect_allele_column', 'A1',
        '--non_effect_allele_column', 'A2',
        '--beta_column', 'BETA',
        '--pvalue_column', 'P',
        '--output_file', f"{output_prefix}.txt"
    ]

    print(f"Command: {' '.join(cmd)}")

    try:
        # Note: In production, actually run the command
        # result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        # print(result.stdout)

        # For now, placeholder
        print(f"  (Execution placeholder - implement with subprocess.run)")

        # Load results (placeholder)
        # results_df = pd.read_csv(f"{output_prefix}.txt", sep='\t')
        results_df = pd.DataFrame()  # Placeholder

        print(f"S-MultiXcan completed")
        print(f"  Output: {output_prefix}.txt")

        return results_df

    except subprocess.CalledProcessError as e:
        print(f"ERROR: S-MultiXcan failed: {e}")
        return pd.DataFrame()


def filter_smultixcan_results(smultixcan_results, bonferroni_threshold=None):
    """
    Filter S-MultiXcan results for genome-wide significant genes.

    Parameters
    ----------
    smultixcan_results : pandas.DataFrame
        S-MultiXcan results
    bonferroni_threshold : float, optional
        Bonferroni threshold. If None, computed as 0.05 / N_genes

    Returns
    -------
    pandas.DataFrame
        Significant genes
    """
    if bonferroni_threshold is None:
        bonferroni_threshold = 0.05 / len(smultixcan_results)

    sig_genes = smultixcan_results[smultixcan_results['pvalue'] < bonferroni_threshold]

    print(f"Cross-tissue significant genes: {len(sig_genes)} (Bonferroni threshold: {bonferroni_threshold:.2e})")

    return sig_genes

