"""
Detect Perturbed Cells Using Outlier Detection

For each perturbation, identify cells with significant phenotypic changes using
outlier detection methods in PCA space computed on differentially expressed genes.
"""

import numpy as np
import pandas as pd
import scanpy as sc
import anndata as ad
from sklearn.svm import OneClassSVM
from sklearn.neighbors import LocalOutlierFactor
from sklearn.ensemble import IsolationForest
import diffxpy.api as de
from typing import Dict, List, Optional, Literal


def detect_perturbed_cells(
    adata: ad.AnnData,
    control_group: str = 'non-targeting',
    gene_col: str = 'gene',
    sgrna_col: str = 'sgRNA',
    n_pcs: int = 4,
    method: Literal['LocalOutlierFactor', 'IsolationForest', 'OneClassSVM'] = 'LocalOutlierFactor',
    min_de_genes: int = 10,
    min_outliers: int = 10,
    pval_threshold: float = 0.05,
    save_plots: bool = True,
    plot_dir: str = 'figures/'
) -> Dict:
    """
    Detect perturbed cells with significant phenotypes using outlier detection.

    For each perturbation vs control:
    1. Run differential expression (t-test)
    2. Select top DE genes (p < pval_threshold)
    3. If ≥min_de_genes found, compute PCA on DE genes
    4. Train outlier detector on control cells
    5. Predict outliers in perturbed cells
    6. If ≥min_outliers detected, flag as "hit"

    Parameters
    ----------
    adata : AnnData
        Log-normalized AnnData (not scaled)
    control_group : str, default='non-targeting'
        Label for non-targeting control
    gene_col : str, default='gene'
        Column in obs with gene/perturbation labels
    sgrna_col : str, default='sgRNA'
        Column in obs with sgRNA labels
    n_pcs : int, default=4
        Number of PCs to compute on DE genes
    method : str, default='LocalOutlierFactor'
        Outlier detection method: 'LocalOutlierFactor', 'IsolationForest', 'OneClassSVM'
    min_de_genes : int, default=10
        Minimum DE genes required to proceed with outlier detection
    min_outliers : int, default=10
        Minimum outliers to call perturbation as "hit"
    pval_threshold : float, default=0.05
        P-value threshold for calling DE genes
    save_plots : bool, default=True
        Generate UMAP/PCA plots for each perturbation
    plot_dir : str, default='figures/'
        Directory to save plots

    Returns
    -------
    results : dict
        Dictionary containing:
        - 'outlier_cells': list of cell barcodes flagged as outliers
        - 'perturbation_summary': DataFrame with hit calls per perturbation
        - 'de_results': dict of DE results per perturbation
        - 'adata_dict': dict of per-perturbation AnnData objects with classifications

    Example
    -------
    >>> results = detect_perturbed_cells(
    ...     adata,
    ...     control_group='non-targeting',
    ...     n_pcs=4,
    ...     method='LocalOutlierFactor'
    ... )
    >>> print(f"Hits detected: {results['perturbation_summary']['is_hit'].sum()}")
    """
    import os
    os.makedirs(plot_dir, exist_ok=True)

    # Initialize results containers
    outlier_cells = []
    perturbation_summary = []
    de_results_dict = {}
    adata_dict = {}

    # Get unique perturbations (exclude control)
    genes = adata.obs[gene_col].unique().tolist()
    genes = [g for g in genes if g != control_group]

    print(f"Detecting perturbed cells for {len(genes)} perturbations...")
    print(f"  Method: {method}")
    print(f"  n_pcs: {n_pcs}")
    print(f"  min_de_genes: {min_de_genes}")
    print(f"  min_outliers: {min_outliers}\n")

    for i, selected_gene in enumerate(genes):
        if (i + 1) % 10 == 0:
            print(f"Processing {i+1}/{len(genes)}: {selected_gene}")

        # Subset to perturbation vs control
        adata_temp = adata[adata.obs[gene_col].isin([selected_gene, control_group])].copy()

        # Run differential expression
        test = de.test.t_test(data=adata_temp, grouping=gene_col)
        de_summary = test.summary()
        de_results_dict[selected_gene] = de_summary

        # Select DE genes
        diff_genes = de_summary[de_summary['pval'] < pval_threshold]['gene'].tolist()

        # Summary metrics
        n_de_genes = len(diff_genes)
        n_perturbed_cells = (adata_temp.obs[gene_col] == selected_gene).sum()
        n_control_cells = (adata_temp.obs[gene_col] == control_group).sum()

        if n_de_genes < min_de_genes:
            # Not enough DE genes, skip outlier detection
            perturbation_summary.append({
                'gene': selected_gene,
                'n_cells': n_perturbed_cells,
                'n_de_genes': n_de_genes,
                'n_outliers': 0,
                'outlier_fraction': 0,
                'is_hit': False,
                'reason': f'insufficient_DE_genes (<{min_de_genes})'
            })
            continue

        # Subset to DE genes only
        adata_temp = adata_temp[:, diff_genes].copy()

        # Compute PCA on DE genes
        sc.tl.pca(adata_temp, svd_solver='arpack', n_comps=n_pcs)

        # Get PCA coordinates
        control_cells = adata_temp.obs[gene_col] == control_group
        perturbed_cells = adata_temp.obs[gene_col] == selected_gene

        x = adata_temp[control_cells].obsm['X_pca']  # Control PCA coords
        y = adata_temp[perturbed_cells].obsm['X_pca']  # Perturbed PCA coords

        # Train outlier detector on control cells
        if method == 'LocalOutlierFactor':
            clf = LocalOutlierFactor(novelty=True, contamination='auto').fit(x)
        elif method == 'IsolationForest':
            clf = IsolationForest(contamination='auto', random_state=42).fit(x)
        elif method == 'OneClassSVM':
            clf = OneClassSVM(nu=0.1).fit(x)
        else:
            raise ValueError(f"Unknown method: {method}")

        # Predict outliers in perturbed cells
        predictions = clf.predict(y)
        n_outliers = (predictions == -1).sum()
        outlier_fraction = n_outliers / len(y)

        # Create full adata for this comparison (with all genes)
        adata_s = adata[adata_temp.obs_names].copy()
        adata_s.obsm = adata_temp.obsm.copy()

        # Add classification
        adata_s.obs['classification'] = 2  # Control label
        adata_s.obs.loc[perturbed_cells, 'classification'] = predictions

        # Convert to categorical for plotting
        adata_s.obs['classification'] = adata_s.obs['classification'].astype('category')

        # Compute neighbors and UMAP for visualization
        sc.pp.neighbors(adata_s, n_pcs=n_pcs)
        sc.tl.umap(adata_s)

        # Save plots
        if save_plots:
            # Check if target gene is in expression matrix
            if selected_gene in adata_s.var_names.tolist():
                sc.pl.umap(
                    adata_s,
                    color=['classification', gene_col, selected_gene, sgrna_col],
                    save=f'_{selected_gene}_new.pdf',
                    show=False
                )
                sc.pl.pca(
                    adata_s,
                    color=['classification', gene_col, selected_gene, sgrna_col],
                    save=f'_{selected_gene}_new.pdf',
                    show=False
                )
            else:
                sc.pl.umap(
                    adata_s,
                    color=['classification', gene_col, sgrna_col],
                    save=f'_{selected_gene}.pdf',
                    show=False
                )
                sc.pl.pca(
                    adata_s,
                    color=['classification', gene_col, sgrna_col],
                    save=f'_{selected_gene}.pdf',
                    show=False
                )

        # Store adata
        adata_dict[selected_gene] = adata_s

        # Check if hit
        is_hit = n_outliers >= min_outliers

        if is_hit:
            # Add outlier cells to list
            outlier_cell_barcodes = adata_s[adata_s.obs['classification'] == -1].obs_names.tolist()
            outlier_cells.extend(outlier_cell_barcodes)

        # Summary
        perturbation_summary.append({
            'gene': selected_gene,
            'n_cells': n_perturbed_cells,
            'n_de_genes': n_de_genes,
            'n_outliers': n_outliers,
            'outlier_fraction': outlier_fraction,
            'is_hit': is_hit,
            'reason': 'hit' if is_hit else f'insufficient_outliers (<{min_outliers})'
        })

    # Convert summary to DataFrame
    summary_df = pd.DataFrame(perturbation_summary)

    # Add control cells to kept cells
    control_cell_barcodes = adata[adata.obs[gene_col] == control_group].obs_names.tolist()
    kept_cells = outlier_cells + control_cell_barcodes

    print(f"\n=== Outlier Detection Summary ===")
    print(f"Total perturbations tested: {len(genes)}")
    print(f"Hits detected (≥{min_outliers} outliers): {summary_df['is_hit'].sum()}")
    print(f"Total outlier cells: {len(outlier_cells)}")
    print(f"Total kept cells (outliers + controls): {len(kept_cells)}")

    results = {
        'outlier_cells': outlier_cells,
        'kept_cells': kept_cells,
        'perturbation_summary': summary_df,
        'de_results': de_results_dict,
        'adata_dict': adata_dict
    }

    return results

