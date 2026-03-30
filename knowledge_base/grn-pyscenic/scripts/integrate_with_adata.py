"""
Integrate pySCENIC results with AnnData object.
"""


def integrate_with_adata(adata, auc_matrix, regulons, output_file="adata_with_scenic.h5ad"):
    """
    Add pySCENIC results to AnnData object for downstream analysis.

    Parameters:
    -----------
    adata : AnnData
        Original AnnData object
    auc_matrix : pd.DataFrame
        AUCell matrix (cells x regulons)
    regulons : list
        List of Regulon objects
    output_file : str
        Path to save updated AnnData (default: "adata_with_scenic.h5ad")

    Returns:
    --------
    adata : AnnData
        Updated AnnData object with regulon activities in .obsm['X_aucell']

    Examples:
    ---------
    >>> adata = integrate_with_adata(adata, auc_matrix, regulons)
    >>> print(f"Added {auc_matrix.shape[1]} regulon activities to adata.obsm['X_aucell']")
    """
    # Add AUCell scores to obsm
    adata.obsm['X_aucell'] = auc_matrix.loc[adata.obs_names].values

    # Store regulon names
    adata.uns['regulon_names'] = list(auc_matrix.columns)

    # Store regulon information
    regulon_info = {}
    for reg in regulons:
        regulon_info[reg.name] = {
            'tf': reg.transcription_factor,
            'n_targets': len(reg.genes),
            'targets': list(reg.genes)[:50]  # Store top 50 targets
        }
    adata.uns['regulons'] = regulon_info

    print(f"✓ Integration completed: regulon activities added to adata.obsm['X_aucell']")
    print(f"  {auc_matrix.shape[1]} regulons added")

    # Save updated AnnData
    adata.write(output_file)
    print(f"Saved: {output_file}")

    return adata

