"""
FUSION TWAS Analysis Wrapper

This module provides a Python wrapper for running FUSION transcriptome-wide
association studies with multiple prediction models.
"""

import pandas as pd
import subprocess
from pathlib import Path
import tempfile


def run_fusion_twas(gwas_sumstats, weights_dir, tissues, ref_ld_panel,
                    models=None, chr_range=None, output_dir="results/fusion/"):
    """
    Run FUSION TWAS analysis.

    Parameters
    ----------
    gwas_sumstats : str or pandas.DataFrame
        Path to GWAS summary statistics or DataFrame
    weights_dir : str
        Directory containing FUSION expression weights
    tissues : list
        List of tissue names to analyze
    ref_ld_panel : str
        Path to LD reference panel directory (e.g., "1000G_EUR/")
    models : list, optional
        Prediction models to use. Default: ["top1", "enet", "lasso", "bslmm"]
    chr_range : range, optional
        Chromosomes to analyze. Default: range(1, 23) (autosomes)
    output_dir : str
        Output directory for results

    Returns
    -------
    pandas.DataFrame
        Combined TWAS results across all tissues
    """
    if models is None:
        models = ["top1", "enet", "lasso", "bslmm"]

    if chr_range is None:
        chr_range = range(1, 23)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # If gwas_sumstats is DataFrame, save to temp file
    if isinstance(gwas_sumstats, pd.DataFrame):
        temp_gwas = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        gwas_sumstats.to_csv(temp_gwas.name, sep='\t', index=False)
        gwas_file = temp_gwas.name
    else:
        gwas_file = gwas_sumstats

    all_results = []

    for tissue in tissues:
        print(f"\nRunning FUSION TWAS for {tissue}...")

        tissue_results = []

        for chrom in chr_range:
            output_prefix = output_path / f"{tissue}_chr{chrom}"

            # FUSION command
            cmd = [
                'Rscript',
                'FUSION.assoc_test.R',
                '--sumstats', gwas_file,
                '--weights', f'{weights_dir}/GTEx.{tissue}.pos',
                '--weights_dir', weights_dir,
                '--ref_ld_chr', f'{ref_ld_panel}/1000G.EUR.',
                '--chr', str(chrom),
                '--out', str(output_prefix)
            ]

            # Add models if specified
            for model in models:
                if model != "top1":
                    cmd.extend(['--models', model])

            print(f"  Chromosome {chrom}...")

            try:
                # Note: In production, actually run the command
                # subprocess.run(cmd, check=True, capture_output=True)

                # For now, placeholder
                print(f"    Command: {' '.join(cmd)}")
                print(f"    (Execution placeholder - implement with subprocess.run)")

                # Load results (placeholder)
                # chr_results = pd.read_csv(f"{output_prefix}.dat", sep='\t')
                # tissue_results.append(chr_results)

            except subprocess.CalledProcessError as e:
                print(f"    ERROR: FUSION failed for chr{chrom}: {e}")
                continue

        # Combine chromosome results
        if tissue_results:
            tissue_df = pd.concat(tissue_results, ignore_index=True)
            tissue_df['TISSUE'] = tissue
            all_results.append(tissue_df)
            print(f"  Completed {tissue}: {len(tissue_df)} genes tested")

    # Combine all tissues
    if all_results:
        fusion_results = pd.concat(all_results, ignore_index=True)
        print(f"\nTotal results: {len(fusion_results)} gene-tissue associations")

        # Save combined results
        output_file = output_path / "fusion_all_tissues.txt"
        fusion_results.to_csv(output_file, sep='\t', index=False)
        print(f"Saved to: {output_file}")

        return fusion_results
    else:
        print("\nERROR: No results generated")
        return pd.DataFrame()


def filter_significant_genes(fusion_results, significance_threshold=None, method="bonferroni"):
    """
    Filter TWAS results for significant genes.

    Parameters
    ----------
    fusion_results : pandas.DataFrame
        FUSION TWAS results
    significance_threshold : float, optional
        Custom significance threshold. If None, computed from method.
    method : str
        Multiple testing correction: "bonferroni" or "fdr" (default: "bonferroni")

    Returns
    -------
    pandas.DataFrame
        Significant genes only
    """
    if significance_threshold is None:
        if method == "bonferroni":
            significance_threshold = 0.05 / len(fusion_results)
        elif method == "fdr":
            from scipy.stats import false_discovery_control
            fusion_results['FDR'] = false_discovery_control(fusion_results['TWAS.P'])
            return fusion_results[fusion_results['FDR'] < 0.05]

    sig_genes = fusion_results[fusion_results['TWAS.P'] < significance_threshold]

    print(f"Significant genes ({method}): {len(sig_genes)}")
    return sig_genes

