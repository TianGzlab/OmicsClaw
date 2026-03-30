"""
Gene Name Corrections

Fix gene name mismatches between sgRNA target names and gene expression matrix.
This commonly occurs with gene symbol updates.
"""

import anndata as ad
from typing import Dict, List, Optional
import pandas as pd


def detect_mismatches(
    adata: ad.AnnData,
    gene_col: str = 'gene'
) -> List[str]:
    """
    Detect gene names in obs that are not present in var_names.

    Parameters
    ----------
    adata : AnnData
        AnnData with 'gene' column in obs
    gene_col : str, default='gene'
        Column name for target gene in obs

    Returns
    -------
    mismatched_genes : list of str
        List of gene names in obs but not in var_names
    """
    if gene_col not in adata.obs.columns:
        print(f"Warning: Column '{gene_col}' not found in adata.obs")
        return []

    genes_in_obs = adata.obs[gene_col].unique().tolist()
    genes_in_var = adata.var_names.tolist()

    mismatched_genes = [g for g in genes_in_obs if g not in genes_in_var]

    if mismatched_genes:
        print(f"Found {len(mismatched_genes)} gene name mismatches:")
        for gene in mismatched_genes:
            print(f"  {gene}")
    else:
        print("No gene name mismatches detected")

    return mismatched_genes


def correct_gene_names(
    adata: ad.AnnData,
    corrections: Dict[str, str],
    gene_col: str = 'gene'
) -> ad.AnnData:
    """
    Apply gene name corrections to obs column.

    Parameters
    ----------
    adata : AnnData
        AnnData with gene column in obs
    corrections : dict
        Dictionary mapping old names to new names
        Example: {'TMEM55A': 'PIP4P2', 'ATP5C1': 'ATP5F1C'}
    gene_col : str, default='gene'
        Column name for target gene in obs

    Returns
    -------
    adata : AnnData
        AnnData with corrected gene names

    Example
    -------
    >>> corrections = {
    ...     'TMEM55A': 'PIP4P2',
    ...     'ATP5C1': 'ATP5F1C',
    ...     'ATP5H': 'ATP5PD'
    ... }
    >>> adata = correct_gene_names(adata, corrections)
    """
    # Check if gene column exists
    if gene_col not in adata.obs.columns:
        print(f"Warning: Column '{gene_col}' not found in adata.obs")
        print("  No corrections applied. Ensure sgRNA mapping is done first.")
        return adata

    if len(corrections) == 0:
        print("No gene name corrections to apply")
        return adata

    print(f"Applying {len(corrections)} gene name corrections:")

    target_genes = adata.obs[gene_col].copy()

    for old_name, new_name in corrections.items():
        n_cells = (target_genes == old_name).sum()
        if n_cells > 0:
            target_genes = target_genes.replace(old_name, new_name)
            print(f"  {old_name} -> {new_name} ({n_cells} cells)")
        else:
            print(f"  {old_name} -> {new_name} (not found)")

    adata.obs[gene_col] = target_genes

    # Verify corrections
    remaining_mismatches = detect_mismatches(adata, gene_col=gene_col)

    if remaining_mismatches:
        print(f"\nWarning: {len(remaining_mismatches)} mismatches remain")
    else:
        print("\nAll gene names corrected successfully")

    return adata


def suggest_corrections(
    adata: ad.AnnData,
    gene_col: str = 'gene',
    use_synonyms: bool = False
) -> Dict[str, str]:
    """
    Suggest gene name corrections based on common aliases.

    Parameters
    ----------
    adata : AnnData
        AnnData with gene column
    gene_col : str, default='gene'
        Column name for target gene
    use_synonyms : bool, default=False
        Use external gene synonym database (requires mygene package)

    Returns
    -------
    suggestions : dict
        Suggested corrections dictionary

    Note
    ----
    For comprehensive synonym lookup, install mygene:
    pip install mygene
    """
    mismatched = detect_mismatches(adata, gene_col=gene_col)

    if not mismatched:
        return {}

    # Common known aliases (human genes)
    known_aliases = {
        'TMEM55A': 'PIP4P2',
        'ATP5C1': 'ATP5F1C',
        'ATP5H': 'ATP5PD',
        'ATP5A1': 'ATP5F1A',
        'ATP5B': 'ATP5F1B',
        'C9orf72': 'C9ORF72',  # Case differences
    }

    suggestions = {}

    for gene in mismatched:
        if gene in known_aliases:
            new_name = known_aliases[gene]
            if new_name in adata.var_names:
                suggestions[gene] = new_name
                print(f"Suggested correction: {gene} -> {new_name}")

    if use_synonyms and len(suggestions) < len(mismatched):
        try:
            import mygene
            mg = mygene.MyGeneInfo()

            remaining = [g for g in mismatched if g not in suggestions]
            results = mg.querymany(remaining, scopes='symbol,alias', fields='symbol', species='human')

            for result in results:
                if 'symbol' in result:
                    old_name = result['query']
                    new_name = result['symbol']
                    if new_name in adata.var_names:
                        suggestions[old_name] = new_name
                        print(f"Suggested correction (from synonym DB): {old_name} -> {new_name}")
        except ImportError:
            print("\nNote: Install mygene for automated synonym lookup:")
            print("  pip install mygene")

    return suggestions

