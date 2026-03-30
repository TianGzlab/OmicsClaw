"""
Map sgRNA Identities to Cells

This module maps sgRNA assignments to cell barcodes, filtering for cells with
single unambiguous sgRNA assignment.
"""

import pandas as pd
import anndata as ad
from typing import Optional


def map_sgrna_to_adata(
    adata: ad.AnnData,
    sgrna_mapping_file: str,
    sgrna_delimiter: str = "_",
    gene_position: int = 0
) -> ad.AnnData:
    """
    Map sgRNA identities to cells and extract target gene names.

    Parameters
    ----------
    adata : AnnData
        AnnData object with cell barcodes as obs_names
    sgrna_mapping_file : str
        Path to TSV file with columns: [cell_barcode, sgRNA_id]
        No header expected, tab-delimited
    sgrna_delimiter : str, default="_"
        Delimiter to split sgRNA ID to extract gene name
        (e.g., "GENE_sgRNA1" -> split by "_" -> "GENE")
    gene_position : int, default=0
        Position of gene name after splitting sgRNA ID

    Returns
    -------
    adata : AnnData
        Filtered AnnData with only mapped cells, adds:
        - adata.obs['sgRNA']: sgRNA identifier
        - adata.obs['gene']: target gene name

    Example
    -------
    >>> adata = map_sgrna_to_adata(
    ...     adata,
    ...     "mapped_single_sgRNA_to_cell_lib1.txt",
    ...     sgrna_delimiter="_"
    ... )
    >>> print(f"Mapping rate: {adata.n_obs}/{adata_original.n_obs}")
    """
    original_n_cells = adata.n_obs

    # Load sgRNA mapping file (no header, tab-delimited)
    # Column 0: cell barcode, Column 1: sgRNA ID
    df_sg_map = pd.read_table(
        sgrna_mapping_file,
        header=None,
        index_col=0
    )

    print(f"Loaded {len(df_sg_map)} sgRNA-cell mappings from {sgrna_mapping_file}")

    # Merge with adata.obs to keep only cells with sgRNA assignment
    mapped = adata.obs.merge(
        df_sg_map,
        left_index=True,
        right_index=True,
        how='inner'
    )

    mapped_cells = mapped.index

    # Filter adata to mapped cells only
    adata = adata[adata.obs.index.isin(mapped_cells), :].copy()

    # Add sgRNA column
    adata.obs['sgRNA'] = mapped[1]

    # Extract gene name from sgRNA ID
    adata.obs['gene'] = adata.obs['sgRNA'].apply(
        lambda x: x.split(sgrna_delimiter)[gene_position]
    )

    mapping_rate = adata.n_obs / original_n_cells * 100

    print(f"  Retained {adata.n_obs}/{original_n_cells} cells with sgRNA mapping ({mapping_rate:.1f}%)")
    print(f"  Unique sgRNAs: {adata.obs['sgRNA'].nunique()}")
    print(f"  Unique genes: {adata.obs['gene'].nunique()}")
    print("✓ sgRNA mapping complete")

    return adata


def check_mapping_quality(adata: ad.AnnData) -> pd.DataFrame:
    """
    Calculate mapping quality metrics.

    Parameters
    ----------
    adata : AnnData
        AnnData with 'gene' and 'sgRNA' in obs

    Returns
    -------
    stats : DataFrame
        Summary statistics: cells per gene, cells per sgRNA
    """
    stats = pd.DataFrame({
        'cells_per_gene': adata.obs.groupby('gene').size(),
        'sgrnas_per_gene': adata.obs.groupby('gene')['sgRNA'].nunique()
    })

    print("\nMapping Quality Metrics:")
    print(f"  Mean cells per gene: {stats['cells_per_gene'].mean():.1f}")
    print(f"  Median cells per gene: {stats['cells_per_gene'].median():.1f}")
    print(f"  Genes with <20 cells: {(stats['cells_per_gene'] < 20).sum()}")
    print(f"  Genes with <10 cells: {(stats['cells_per_gene'] < 10).sum()}")

    return stats

