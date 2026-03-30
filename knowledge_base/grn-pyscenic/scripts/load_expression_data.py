"""
Load and preprocess single-cell expression data for pySCENIC analysis.
"""

import pandas as pd
import scanpy as sc


def load_expression_data(file_path):
    """
    Load single-cell expression data from various formats.

    Parameters:
    -----------
    file_path : str
        Path to expression data file (.h5ad, .loom, .csv, or .tsv)

    Returns:
    --------
    adata : AnnData
        AnnData object with filtered data
    ex_matrix : pd.DataFrame
        Expression matrix (cells x genes) as DataFrame

    Examples:
    ---------
    >>> adata, ex_matrix = load_expression_data("scrnaseq_data.h5ad")
    >>> print(f"Loaded {adata.n_obs} cells x {adata.n_vars} genes")
    """
    if file_path.endswith('.h5ad'):
        adata = sc.read_h5ad(file_path)
    elif file_path.endswith('.loom'):
        adata = sc.read_loom(file_path)
    else:
        # Assume CSV/TSV
        df = pd.read_csv(file_path, index_col=0)
        # Transpose if genes are rows
        if df.shape[0] > df.shape[1]:
            df = df.T
        adata = sc.AnnData(df)

    print(f"Loaded data: {adata.n_obs} cells x {adata.n_vars} genes")

    # Basic filtering
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)

    print(f"After filtering: {adata.n_obs} cells x {adata.n_vars} genes")
    print(f"✓ Data loaded successfully: {adata.n_obs} cells, {adata.n_vars} genes")

    # Get expression matrix as DataFrame (cells x genes)
    if hasattr(adata.X, 'toarray'):
        ex_matrix = pd.DataFrame(adata.X.toarray(),
                                  index=adata.obs_names,
                                  columns=adata.var_names)
    else:
        ex_matrix = pd.DataFrame(adata.X,
                                  index=adata.obs_names,
                                  columns=adata.var_names)

    return adata, ex_matrix

