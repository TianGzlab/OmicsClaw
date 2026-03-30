"""
S-PrediXcan TWAS Analysis Wrapper

This module provides a Python wrapper for running S-PrediXcan transcriptome-wide
association studies using GWAS summary statistics.
"""

import pandas as pd
import subprocess
from pathlib import Path
import time


def run_spredixxcan(gwas_sumstats, weights_db, tissue, covariance_matrix, output_prefix="results/spredixxcan/output"):
    """
    Run S-PrediXcan TWAS analysis for a single tissue.

    Parameters
    ----------
    gwas_sumstats : str
        Path to GWAS summary statistics in MetaXcan format
    weights_db : str
        Path to expression weights database (.db file)
        Example: "weights/GTEx_v8/gtex_v8_mashr_Artery_Coronary.db"
    tissue : str
        Tissue name for labeling
    covariance_matrix : str
        Path to covariance matrix for the tissue
        Example: "weights/GTEx_v8/gtex_v8_Artery_Coronary_covariance.txt.gz"
    output_prefix : str
        Output file prefix

    Returns
    -------
    dict
        Dictionary with 'results' (DataFrame) and 'runtime' (float)
    """
    output_path = Path(output_prefix).parent
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Running S-PrediXcan for {tissue}...")

    start_time = time.time()

    # S-PrediXcan command
    cmd = [
        'python',
        '-m', 'metaxcan.SPrediXcan',
        '--model_db_path', weights_db,
        '--covariance', covariance_matrix,
        '--gwas_file', gwas_sumstats,
        '--snp_column', 'SNP',
        '--effect_allele_column', 'A1',
        '--non_effect_allele_column', 'A2',
        '--beta_column', 'BETA',
        '--pvalue_column', 'P',
        '--output_file', f"{output_prefix}.csv"
    ]

    print(f"Command: {' '.join(cmd)}")

    try:
        # Note: In production, actually run the command
        # result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        # print(result.stdout)

        # For now, placeholder
        print(f"  (Execution placeholder - implement with subprocess.run)")

        # Load results (placeholder)
        # results_df = pd.read_csv(f"{output_prefix}.csv")
        results_df = pd.DataFrame()  # Placeholder

    except subprocess.CalledProcessError as e:
        print(f"ERROR: S-PrediXcan failed: {e}")
        return {'results': pd.DataFrame(), 'runtime': 0}

    runtime = time.time() - start_time

    print(f"S-PrediXcan completed in {runtime/60:.1f} minutes")

    return {
        'results': results_df,
        'runtime': runtime
    }


def run_spredixxcan_multi_tissue(gwas_sumstats, weights_dir, tissues, output_dir="results/spredixxcan/"):
    """
    Run S-PrediXcan for multiple tissues.

    Parameters
    ----------
    gwas_sumstats : str
        Path to GWAS summary statistics
    weights_dir : str
        Directory containing expression weights databases
    tissues : list
        List of tissue names
    output_dir : str
        Output directory

    Returns
    -------
    pandas.DataFrame
        Combined results across all tissues
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    all_results = []

    for tissue in tissues:
        weights_db = f"{weights_dir}/gtex_v8_mashr_{tissue}.db"
        covariance = f"{weights_dir}/gtex_v8_{tissue}_covariance.txt.gz"
        output_prefix = output_path / tissue

        result = run_spredixxcan(
            gwas_sumstats=gwas_sumstats,
            weights_db=weights_db,
            tissue=tissue,
            covariance_matrix=covariance,
            output_prefix=str(output_prefix)
        )

        if not result['results'].empty:
            result['results']['TISSUE'] = tissue
            all_results.append(result['results'])

    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        combined_file = output_path / "spredixxcan_all_tissues.csv"
        combined.to_csv(combined_file, index=False)
        print(f"\nSaved combined results: {combined_file}")
        return combined
    else:
        print("\nERROR: No results generated")
        return pd.DataFrame()

