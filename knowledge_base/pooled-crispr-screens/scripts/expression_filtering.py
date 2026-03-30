"""
Expression-Based Gene Filtering

Filter genes by mean expression across sgRNA groups to remove lowly expressed
genes that add noise without information.
"""

from typing import Optional
import numpy as np
import pandas as pd
import anndata as ad


def grouped_obs_mean(
    adata: ad.AnnData,
    group_key: str,
    layer: Optional[str] = None,
    gene_symbols: Optional[str] = None
) -> pd.DataFrame:
    """
    Calculate mean expression for each gene within each group.

    Parameters
    ----------
    adata : AnnData
        Input AnnData object
    group_key : str
        Column in adata.obs to group by (e.g., 'sgRNA' or 'gene')
    layer : str, optional
        If provided, use this layer instead of X
    gene_symbols : str, optional
        Not currently used, for future compatibility

    Returns
    -------
    mean_exp : DataFrame
        DataFrame with genes as rows, groups as columns, mean expression as values

    Example
    -------
    >>> mean_exp = grouped_obs_mean(adata, 'sgRNA')
    >>> # Returns: genes x sgRNAs matrix of mean expression
    """
    if layer is not None:
        getX = lambda x: x.layers[layer]
    else:
        getX = lambda x: x.X

    grouped = adata.obs.groupby(group_key)

    out = pd.DataFrame(
        np.zeros((adata.shape[1], len(grouped)), dtype=np.float64),
        columns=list(grouped.groups.keys()),
        index=adata.var_names
    )

    for group, idx in grouped.indices.items():
        X = getX(adata[idx])
        out[group] = np.ravel(X.mean(axis=0, dtype=np.float64))

    return out


def filter_by_expression(
    adata: ad.AnnData,
    group_key: str = 'sgRNA',
    min_mean_expression: float = 0.5,
    require_expression_in: str = 'any'
) -> ad.AnnData:
    """
    Filter genes by mean expression across groups.

    Parameters
    ----------
    adata : AnnData
        Input AnnData object
    group_key : str, default='sgRNA'
        Column to group by for calculating mean expression
    min_mean_expression : float, default=0.5
        Minimum mean expression threshold
    require_expression_in : str, default='any'
        'any': keep gene if expressed in any group
        'all': keep gene if expressed in all groups

    Returns
    -------
    adata_filtered : AnnData
        Filtered AnnData with only expressed genes

    Example
    -------
    >>> adata_filtered = filter_by_expression(
    ...     adata,
    ...     group_key='sgRNA',
    ...     min_mean_expression=0.5
    ... )
    """
    original_n_genes = adata.n_vars

    print(f"Filtering genes by expression (group_key='{group_key}')...")
    print(f"  min_mean_expression: {min_mean_expression}")
    print(f"  require_expression_in: {require_expression_in}")

    # Calculate mean expression per group
    mean_exp = grouped_obs_mean(adata, group_key)

    # Filter genes
    if require_expression_in == 'any':
        keep_genes = (mean_exp > min_mean_expression).any(axis=1)
    elif require_expression_in == 'all':
        keep_genes = (mean_exp > min_mean_expression).all(axis=1)
    else:
        raise ValueError(f"require_expression_in must be 'any' or 'all', got {require_expression_in}")

    adata_filtered = adata[:, keep_genes].copy()

    n_retained = adata_filtered.n_vars
    n_filtered = original_n_genes - n_retained
    retention_rate = n_retained / original_n_genes * 100

    print(f"\nExpression Filtering Summary:")
    print(f"  Original genes: {original_n_genes}")
    print(f"  Retained genes: {n_retained} ({retention_rate:.1f}%)")
    print(f"  Filtered genes: {n_filtered}")
    print("✓ Expression filtering complete")

    return adata_filtered


def summarize_expression(
    adata: ad.AnnData,
    group_key: str = 'sgRNA'
) -> pd.DataFrame:
    """
    Summarize expression statistics across groups.

    Parameters
    ----------
    adata : AnnData
        Input AnnData
    group_key : str
        Column to group by

    Returns
    -------
    summary : DataFrame
        Summary statistics for each gene
    """
    mean_exp = grouped_obs_mean(adata, group_key)

    summary = pd.DataFrame({
        'mean_across_groups': mean_exp.mean(axis=1),
        'max_across_groups': mean_exp.max(axis=1),
        'min_across_groups': mean_exp.min(axis=1),
        'expressed_in_n_groups': (mean_exp > 0).sum(axis=1),
        'expressed_in_frac_groups': (mean_exp > 0).sum(axis=1) / mean_exp.shape[1]
    })

    return summary

