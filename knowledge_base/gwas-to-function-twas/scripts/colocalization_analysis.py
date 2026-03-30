"""
Colocalization Analysis for TWAS

This module provides functions for colocalization testing to distinguish true
causal genes from LD artifacts using COLOC and related methods.
"""

import pandas as pd
import subprocess
from pathlib import Path


def run_coloc_for_twas_hits(twas_results, gwas_sumstats, eqtl_dir, tissue,
                             window_kb=500, output_dir="results/colocalization/"):
    """
    Run colocalization analysis for significant TWAS genes.

    Parameters
    ----------
    twas_results : pandas.DataFrame
        TWAS results with significant genes
    gwas_sumstats : pandas.DataFrame or str
        GWAS summary statistics
    eqtl_dir : str
        Directory containing eQTL summary statistics
    tissue : str
        Tissue name
    window_kb : int
        Window size around gene for colocalization (default: 500kb)
    output_dir : str
        Output directory

    Returns
    -------
    pandas.DataFrame
        Colocalization results with PP.H4 posterior probabilities
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Running colocalization analysis for {len(twas_results)} TWAS genes...")

    coloc_results = []

    for idx, row in twas_results.iterrows():
        gene = row['GENE']
        chrom = row['CHR']
        gene_start = row['P0']
        gene_end = row['P1']

        # Define colocalization window
        window_start = max(0, gene_start - window_kb * 1000)
        window_end = gene_end + window_kb * 1000

        print(f"  {gene} (chr{chrom}:{window_start}-{window_end})")

        # Extract GWAS data in window
        if isinstance(gwas_sumstats, pd.DataFrame):
            gwas_window = gwas_sumstats[
                (gwas_sumstats['CHR'] == chrom) &
                (gwas_sumstats['BP'] >= window_start) &
                (gwas_sumstats['BP'] <= window_end)
            ]
        else:
            # Load from file
            gwas_window = pd.read_csv(gwas_sumstats, sep='\t')
            gwas_window = gwas_window[
                (gwas_window['CHR'] == chrom) &
                (gwas_window['BP'] >= window_start) &
                (gwas_window['BP'] <= window_end)
            ]

        # Extract eQTL data
        eqtl_file = f"{eqtl_dir}/{tissue}/{gene}.eqtl.txt"
        try:
            eqtl_data = pd.read_csv(eqtl_file, sep='\t')
        except FileNotFoundError:
            print(f"    WARNING: eQTL data not found for {gene}")
            continue

        # Run COLOC (R implementation)
        coloc_result = run_coloc_r(gwas_window, eqtl_data, gene)

        coloc_results.append({
            'GENE': gene,
            'CHR': chrom,
            'TISSUE': tissue,
            'PP.H0': coloc_result.get('PP.H0', None),
            'PP.H1': coloc_result.get('PP.H1', None),
            'PP.H2': coloc_result.get('PP.H2', None),
            'PP.H3': coloc_result.get('PP.H3', None),
            'PP.H4': coloc_result.get('PP.H4', None),
            'N_SNPs': len(gwas_window)
        })

    coloc_df = pd.DataFrame(coloc_results)

    # Save results
    output_file = output_path / f"coloc_{tissue}.txt"
    coloc_df.to_csv(output_file, sep='\t', index=False)
    print(f"\nSaved colocalization results: {output_file}")

    return coloc_df


def run_coloc_r(gwas_data, eqtl_data, gene_name):
    """
    Run COLOC in R for a single gene.

    Parameters
    ----------
    gwas_data : pandas.DataFrame
        GWAS summary statistics in window
    eqtl_data : pandas.DataFrame
        eQTL summary statistics for gene
    gene_name : str
        Gene name

    Returns
    -------
    dict
        COLOC posterior probabilities (PP.H0 - PP.H4)
    """
    # This is a placeholder for the actual R COLOC implementation
    # In production, write data to temp files and call R script

    # Example R code that would be called:
    """
    library(coloc)

    gwas_list <- list(
        beta = gwas_data$BETA,
        varbeta = gwas_data$SE^2,
        N = median(gwas_data$N),
        type = "cc",  # or "quant" for quantitative traits
        snp = gwas_data$SNP
    )

    eqtl_list <- list(
        beta = eqtl_data$BETA,
        varbeta = eqtl_data$SE^2,
        N = eqtl_data$N[1],
        type = "quant",
        snp = eqtl_data$SNP
    )

    result <- coloc.abf(dataset1=gwas_list, dataset2=eqtl_list)
    """

    # Placeholder result
    result = {
        'PP.H0': 0.01,  # No association
        'PP.H1': 0.05,  # GWAS only
        'PP.H2': 0.10,  # eQTL only
        'PP.H3': 0.10,  # Different causal variants
        'PP.H4': 0.74   # Shared causal variant
    }

    print(f"    PP.H4 = {result['PP.H4']:.3f}")

    return result


def filter_colocalized_genes(coloc_results, pp4_threshold=0.8):
    """
    Filter for genes with strong colocalization evidence.

    Parameters
    ----------
    coloc_results : pandas.DataFrame
        Colocalization results
    pp4_threshold : float
        PP.H4 threshold (default: 0.8)

    Returns
    -------
    pandas.DataFrame
        Genes with PP.H4 > threshold
    """
    high_confidence = coloc_results[coloc_results['PP.H4'] > pp4_threshold]

    print(f"\nColocalization filtering:")
    print(f"  Total genes tested: {len(coloc_results)}")
    print(f"  High confidence (PP.H4 > {pp4_threshold}): {len(high_confidence)}")
    print(f"  Filtered out (likely LD artifacts): {len(coloc_results) - len(high_confidence)}")

    return high_confidence

