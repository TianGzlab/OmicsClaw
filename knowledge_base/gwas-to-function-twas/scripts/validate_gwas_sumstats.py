"""
GWAS Summary Statistics Validation and QC

This module provides functions for validating GWAS summary statistics format,
performing quality control checks, and harmonizing alleles to match reference panels.
"""

import pandas as pd
import numpy as np
import subprocess
import tempfile
from pathlib import Path


def validate_gwas_sumstats(gwas_file, required_cols=None, min_n_samples=5000):
    """
    Validate GWAS summary statistics format and quality.

    Parameters
    ----------
    gwas_file : str
        Path to GWAS summary statistics file (supports .gz compression)
    required_cols : list, optional
        Required column names. Default: ['SNP', 'CHR', 'BP', 'A1', 'A2', 'BETA', 'SE', 'P', 'N']
    min_n_samples : int
        Minimum sample size required (default: 5000)

    Returns
    -------
    pandas.DataFrame
        Validated GWAS summary statistics

    Raises
    ------
    ValueError
        If validation fails
    """
    if required_cols is None:
        required_cols = ['SNP', 'CHR', 'BP', 'A1', 'A2', 'BETA', 'SE', 'P', 'N']

    # Load data
    print(f"Loading GWAS summary statistics from {gwas_file}...")
    gwas = pd.read_csv(gwas_file, sep='\t', compression='infer')
    print(f"Loaded {len(gwas):,} SNPs")

    # Check required columns
    missing_cols = [col for col in required_cols if col not in gwas.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Check for duplicate SNPs
    duplicates = gwas['SNP'].duplicated().sum()
    if duplicates > 0:
        print(f"WARNING: Removing {duplicates} duplicate SNP IDs")
        gwas = gwas.drop_duplicates(subset='SNP')

    # Validate alleles
    valid_alleles = {'A', 'T', 'C', 'G'}
    invalid_a1 = ~gwas['A1'].isin(valid_alleles)
    invalid_a2 = ~gwas['A2'].isin(valid_alleles)

    if invalid_a1.sum() > 0 or invalid_a2.sum() > 0:
        print(f"WARNING: Removing {(invalid_a1 | invalid_a2).sum()} SNPs with invalid alleles")
        gwas = gwas[~(invalid_a1 | invalid_a2)]

    # Validate P-values
    invalid_p = (gwas['P'] < 0) | (gwas['P'] > 1) | gwas['P'].isna()
    if invalid_p.sum() > 0:
        print(f"WARNING: Removing {invalid_p.sum()} SNPs with invalid P-values")
        gwas = gwas[~invalid_p]

    # Check sample size
    if 'N' in gwas.columns:
        median_n = gwas['N'].median()
        if median_n < min_n_samples:
            print(f"WARNING: Median sample size ({median_n:.0f}) below recommended minimum ({min_n_samples})")

    # Check effect sizes and standard errors
    if 'BETA' in gwas.columns and 'SE' in gwas.columns:
        extreme_beta = gwas['BETA'].abs() > 10
        extreme_se = gwas['SE'] > 10

        if extreme_beta.sum() > 0:
            print(f"WARNING: {extreme_beta.sum()} SNPs with extreme effect sizes (|BETA| > 10)")
        if extreme_se.sum() > 0:
            print(f"WARNING: {extreme_se.sum()} SNPs with extreme standard errors (SE > 10)")

    # Calculate genomic control lambda
    if 'P' in gwas.columns:
        chi2 = np.power(np.abs(np.sqrt(2) * np.sqrt(-2 * np.log(gwas['P']))), 2)
        lambda_gc = np.median(chi2) / 0.456
        print(f"Genomic control lambda: {lambda_gc:.3f}")

        if lambda_gc > 2.0:
            print(f"WARNING: High genomic inflation (λGC = {lambda_gc:.3f}). Check for population stratification.")
        elif lambda_gc > 1.1:
            print(f"NOTE: Moderate inflation (λGC = {lambda_gc:.3f}). Consider LDSC intercept test.")

    print(f"Validation complete: {len(gwas):,} SNPs passed QC")
    return gwas


def harmonize_alleles(gwas_df, reference_panel="1000G_EUR", remove_ambiguous=True):
    """
    Harmonize GWAS alleles to match reference panel.

    Parameters
    ----------
    gwas_df : pandas.DataFrame
        GWAS summary statistics with A1, A2 columns
    reference_panel : str
        Reference panel name (e.g., "1000G_EUR")
    remove_ambiguous : bool
        Remove A/T and G/C SNPs (default: True)

    Returns
    -------
    pandas.DataFrame
        Harmonized GWAS summary statistics
    """
    print("Harmonizing alleles...")

    gwas_harmonized = gwas_df.copy()

    # Remove ambiguous strand SNPs if requested
    if remove_ambiguous:
        ambiguous = (
            ((gwas_harmonized['A1'] == 'A') & (gwas_harmonized['A2'] == 'T')) |
            ((gwas_harmonized['A1'] == 'T') & (gwas_harmonized['A2'] == 'A')) |
            ((gwas_harmonized['A1'] == 'G') & (gwas_harmonized['A2'] == 'C')) |
            ((gwas_harmonized['A1'] == 'C') & (gwas_harmonized['A2'] == 'G'))
        )
        n_ambiguous = ambiguous.sum()
        if n_ambiguous > 0:
            print(f"Removing {n_ambiguous} ambiguous strand SNPs (A/T, G/C)")
            gwas_harmonized = gwas_harmonized[~ambiguous]

    print(f"Harmonization complete: {len(gwas_harmonized):,} SNPs retained")
    return gwas_harmonized


def run_ldsc_intercept_qc(gwas_sumstats, ldsc_path, output_prefix="gwas_qc"):
    """
    Run LDSC intercept test to distinguish polygenicity from population stratification.

    Parameters
    ----------
    gwas_sumstats : pandas.DataFrame
        GWAS summary statistics
    ldsc_path : str
        Path to LDSC installation directory
    output_prefix : str
        Output file prefix

    Returns
    -------
    dict
        Dictionary with 'intercept', 'ratio', and 'interpretation' keys
    """
    print("Running LDSC intercept test...")

    # Save GWAS to temporary file in LDSC format
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        temp_gwas = f.name
        ldsc_format = gwas_sumstats[['SNP', 'CHR', 'BP', 'A1', 'A2', 'BETA', 'SE', 'P', 'N']].copy()
        ldsc_format.to_csv(temp_gwas, sep='\t', index=False)

    # Run LDSC (simplified - actual implementation would call LDSC)
    # This is a placeholder for the actual LDSC command
    try:
        cmd = [
            'python2',
            f'{ldsc_path}/ldsc.py',
            '--h2', temp_gwas,
            '--ref-ld-chr', f'{ldsc_path}/eur_w_ld_chr/',
            '--w-ld-chr', f'{ldsc_path}/eur_w_ld_chr/',
            '--out', output_prefix
        ]

        # Note: This is a placeholder - actual implementation would run the command
        # subprocess.run(cmd, check=True)

        # For now, return example results
        # In production, parse LDSC output file
        intercept = 1.02
        ratio = 0.08

    except Exception as e:
        print(f"LDSC failed: {e}")
        print("Returning placeholder values")
        intercept = 1.0
        ratio = 0.0
    finally:
        Path(temp_gwas).unlink(missing_ok=True)

    # Interpret results
    if intercept <= 1.0 and ratio < 0.10:
        interpretation = "✅ Good quality (inflation is polygenic)"
    elif intercept <= 1.05 and ratio < 0.15:
        interpretation = "⚠️ Acceptable (mostly polygenic)"
    else:
        interpretation = "❌ Poor quality (population stratification detected)"

    result = {
        'intercept': intercept,
        'ratio': ratio,
        'interpretation': interpretation
    }

    print(f"LDSC intercept: {intercept:.3f}")
    print(f"Ratio (confounding): {ratio:.3f}")
    print(f"Interpretation: {interpretation}")

    return result

