"""
Fast t-test screening for all perturbations vs non-targeting controls

This script performs rapid differential expression testing for genome-wide
CRISPR screens to identify preliminary hits for downstream validation.
"""

import scanpy as sc
import diffxpy.api as de
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional, List


def screen_all_perturbations(
    adata,
    control_group: str = 'non-targeting',
    gene_col: str = 'gene',
    test_method: str = 't-test',
    min_cells_per_group: int = 20,
    fdr_threshold: float = 0.05,
    output_dir: str = 'results/initial_screening/',
    verbose: bool = True
) -> Dict[str, pd.DataFrame]:
    """
    Run DE screening for all perturbations vs controls using t-test

    Parameters
    ----------
    adata : AnnData
        Annotated data object with log-normalized counts
    control_group : str
        Name of non-targeting control group in adata.obs[gene_col]
    gene_col : str
        Column in adata.obs containing perturbation identities
    test_method : str
        Statistical test to use ('t-test', 'wilcoxon')
    min_cells_per_group : int
        Minimum cells required per group to run test
    fdr_threshold : float
        FDR threshold for significance
    output_dir : str
        Directory to save results
    verbose : bool
        Print progress messages

    Returns
    -------
    dict
        Dictionary mapping perturbation name to DE results DataFrame
        Each DataFrame contains: gene, log2fc, pval, qval, mean_control, mean_perturbed
    """

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Get list of perturbations (excluding controls)
    perturbations = [g for g in adata.obs[gene_col].unique()
                     if g != control_group]

    if verbose:
        print(f"Testing {len(perturbations)} perturbations vs {control_group} controls")
        print(f"Test method: {test_method}")
        print(f"Minimum cells per group: {min_cells_per_group}")

    # Count control cells
    n_control = (adata.obs[gene_col] == control_group).sum()
    if n_control < min_cells_per_group:
        raise ValueError(f"Insufficient control cells: {n_control} < {min_cells_per_group}")

    results = {}
    skipped = []

    for i, gene in enumerate(perturbations):
        if verbose and (i+1) % 50 == 0:
            print(f"  Processing {i+1}/{len(perturbations)} perturbations...")

        # Check minimum cells
        n_perturbed = (adata.obs[gene_col] == gene).sum()

        if n_perturbed < min_cells_per_group:
            if verbose:
                print(f"  Skipping {gene}: only {n_perturbed} cells (< {min_cells_per_group})")
            skipped.append(gene)
            continue

        # Subset to perturbation vs control
        adata_sub = adata[adata.obs[gene_col].isin([gene, control_group])].copy()

        try:
            # Run differential expression test
            if test_method == 't-test':
                test = de.test.t_test(
                    data=adata_sub,
                    grouping=gene_col,
                    is_logged=True
                )
            elif test_method == 'wilcoxon':
                test = de.test.wilcoxon(
                    data=adata_sub,
                    grouping=gene_col
                )
            else:
                raise ValueError(f"Unknown test method: {test_method}")

            # Get results summary
            de_df = test.summary()

            # Calculate mean expression in each group (handle both sparse and dense matrices)
            control_mean = np.asarray(adata_sub[adata_sub.obs[gene_col] == control_group].X.mean(axis=0)).flatten()
            perturbed_mean = np.asarray(adata_sub[adata_sub.obs[gene_col] == gene].X.mean(axis=0)).flatten()

            # Add to results dataframe
            de_df['mean_control'] = control_mean
            de_df['mean_perturbed'] = perturbed_mean
            de_df['n_cells_control'] = n_control
            de_df['n_cells_perturbed'] = n_perturbed

            # Sort by p-value
            de_df = de_df.sort_values('pval')

            # Save to file
            output_file = Path(output_dir) / f"{gene}_ttest.csv"
            de_df.to_csv(output_file, index=False)

            results[gene] = de_df

        except Exception as e:
            if verbose:
                print(f"  Error processing {gene}: {str(e)}")
            skipped.append(gene)

    if verbose:
        print(f"\nCompleted: {len(results)} perturbations tested")
        print(f"Skipped: {len(skipped)} perturbations")
        if len(skipped) > 0 and len(skipped) <= 10:
            print(f"  Skipped: {', '.join(skipped)}")

    return results


def call_hits(
    de_results: Dict[str, pd.DataFrame],
    min_de_genes: int = 10,
    fdr_threshold: float = 0.05,
    min_abs_log2fc: float = 0.5,
    top_n: Optional[int] = None
) -> pd.DataFrame:
    """
    Call preliminary hits based on number of DE genes

    Parameters
    ----------
    de_results : dict
        Dictionary of DE results from screen_all_perturbations
    min_de_genes : int
        Minimum number of DE genes to call hit
    fdr_threshold : float
        FDR threshold for significance
    min_abs_log2fc : float
        Minimum absolute log2 fold-change
    top_n : int, optional
        Return only top N hits (by number of DE genes)

    Returns
    -------
    pd.DataFrame
        Hit summary with columns: gene, n_de_genes, n_cells, top_de_gene, max_log2fc
    """

    hit_summary = []

    for gene, de_df in de_results.items():
        # Filter to significant genes
        sig_genes = de_df[
            (de_df['qval'] < fdr_threshold) &
            (np.abs(de_df['log2fc']) > min_abs_log2fc)
        ]

        n_de_genes = len(sig_genes)

        # Get top DE gene info
        if n_de_genes > 0:
            top_gene = sig_genes.iloc[0]['gene']
            max_log2fc = sig_genes.iloc[0]['log2fc']
        else:
            top_gene = None
            max_log2fc = 0

        hit_summary.append({
            'perturbation': gene,
            'n_de_genes': n_de_genes,
            'n_cells_perturbed': de_df['n_cells_perturbed'].iloc[0] if len(de_df) > 0 else 0,
            'n_cells_control': de_df['n_cells_control'].iloc[0] if len(de_df) > 0 else 0,
            'top_de_gene': top_gene,
            'top_de_log2fc': max_log2fc
        })

    hit_df = pd.DataFrame(hit_summary)

    # Filter to hits
    hit_df = hit_df[hit_df['n_de_genes'] >= min_de_genes].copy()

    # Sort by number of DE genes
    hit_df = hit_df.sort_values('n_de_genes', ascending=False)

    if top_n is not None:
        hit_df = hit_df.head(top_n)

    return hit_df


def summarize_screening_results(
    de_results: Dict[str, pd.DataFrame],
    output_file: str = 'results/screening_summary.txt'
):
    """
    Generate summary statistics for screening results

    Parameters
    ----------
    de_results : dict
        Dictionary of DE results from screen_all_perturbations
    output_file : str
        Path to save summary text file
    """

    n_perturbations = len(de_results)

    # Count DE genes per perturbation
    n_de_per_pert = []
    for gene, de_df in de_results.items():
        n_de = (de_df['qval'] < 0.05).sum()
        n_de_per_pert.append(n_de)

    n_de_per_pert = np.array(n_de_per_pert)

    # Generate summary
    summary = f"""
CRISPR Screen Initial Screening Summary
========================================

Total perturbations tested: {n_perturbations}

DE genes per perturbation:
  Mean: {n_de_per_pert.mean():.1f}
  Median: {np.median(n_de_per_pert):.0f}
  Min: {n_de_per_pert.min()}
  Max: {n_de_per_pert.max()}

Hit rate (≥10 DE genes): {(n_de_per_pert >= 10).sum()} / {n_perturbations} ({(n_de_per_pert >= 10).sum()/n_perturbations*100:.1f}%)
Hit rate (≥20 DE genes): {(n_de_per_pert >= 20).sum()} / {n_perturbations} ({(n_de_per_pert >= 20).sum()/n_perturbations*100:.1f}%)
Hit rate (≥50 DE genes): {(n_de_per_pert >= 50).sum()} / {n_perturbations} ({(n_de_per_pert >= 50).sum()/n_perturbations*100:.1f}%)

Distribution of DE genes:
  0 DE genes: {(n_de_per_pert == 0).sum()}
  1-9 DE genes: {((n_de_per_pert > 0) & (n_de_per_pert < 10)).sum()}
  10-49 DE genes: {((n_de_per_pert >= 10) & (n_de_per_pert < 50)).sum()}
  50-99 DE genes: {((n_de_per_pert >= 50) & (n_de_per_pert < 100)).sum()}
  ≥100 DE genes: {(n_de_per_pert >= 100).sum()}
"""

    print(summary)

    # Save to file
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        f.write(summary)

    print(f"Summary saved to: {output_file}")


if __name__ == "__main__":
    # Example usage
    import argparse

    parser = argparse.ArgumentParser(description='Screen all perturbations for DE')
    parser.add_argument('--adata', required=True, help='Path to AnnData h5ad file')
    parser.add_argument('--control', default='non-targeting', help='Control group name')
    parser.add_argument('--gene-col', default='gene', help='Column with perturbation IDs')
    parser.add_argument('--min-cells', type=int, default=20, help='Minimum cells per group')
    parser.add_argument('--output-dir', default='results/initial_screening/', help='Output directory')

    args = parser.parse_args()

    # Load data
    print(f"Loading data from {args.adata}...")
    adata = sc.read_h5ad(args.adata)

    # Run screening
    de_results = screen_all_perturbations(
        adata,
        control_group=args.control,
        gene_col=args.gene_col,
        min_cells_per_group=args.min_cells,
        output_dir=args.output_dir
    )

    # Call hits
    hits = call_hits(de_results, min_de_genes=10)
    hits.to_csv(f"{args.output_dir}/hit_summary.csv", index=False)
    print(f"\nIdentified {len(hits)} preliminary hits")

    # Generate summary
    summarize_screening_results(de_results, output_file=f"{args.output_dir}/screening_summary.txt")

