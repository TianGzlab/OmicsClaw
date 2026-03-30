"""
Batch Integration Using scVI, scANVI, and Harmony

This module implements state-of-the-art batch integration methods for single-cell
RNA-seq data, including scVI (unsupervised), scANVI (semi-supervised), and Harmony.

For methodology and best practices, see references/integration_methods.md

Functions:
  - run_scvi_integration(): Unsupervised deep learning integration with scVI
  - run_scanvi_integration(): Semi-supervised integration with cell type labels
  - run_harmony_integration(): Fast linear integration with Harmony
  - setup_for_integration(): Prepare AnnData object for integration

Requirements:
  - scvi-tools (for scVI/scANVI): pip install scvi-tools
  - harmonypy (for Harmony): pip install harmonypy
  - GPU recommended for scVI/scANVI (10-20x faster)
"""

import scanpy as sc
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Union, List, Dict
import warnings


def setup_for_integration(
    adata: sc.AnnData,
    batch_key: str,
    highly_variable_genes: bool = True,
    n_top_genes: int = 2000,
    inplace: bool = True
) -> Optional[sc.AnnData]:
    """
    Prepare AnnData object for integration.

    Ensures data is properly formatted for scVI/scANVI/Harmony integration.

    Parameters
    ----------
    adata : AnnData
        AnnData object to prepare
    batch_key : str
        Column in adata.obs containing batch labels
    highly_variable_genes : bool, optional
        Subset to highly variable genes (default: True)
    n_top_genes : int, optional
        Number of HVGs to select (default: 2000)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        Prepared AnnData object if inplace=False, else None

    Notes
    -----
    - Ensures raw counts are available for scVI/scANVI
    - Selects highly variable genes if requested
    - Validates batch column exists
    """
    if not inplace:
        adata = adata.copy()

    # Check batch column exists
    if batch_key not in adata.obs.columns:
        raise ValueError(f"Batch key '{batch_key}' not found in adata.obs")

    n_batches = adata.obs[batch_key].nunique()
    print(f"\nPreparing data for integration:")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")
    print(f"  Batches: {n_batches} ({batch_key})")

    # Ensure raw counts are available
    if adata.raw is None and 'counts' not in adata.layers:
        warnings.warn(
            "No raw counts found. Integration methods require raw counts. "
            "If adata.X contains raw counts, they will be used."
        )

    # Select highly variable genes if requested
    if highly_variable_genes:
        if 'highly_variable' not in adata.var.columns:
            print(f"  Computing {n_top_genes} highly variable genes...")
            sc.pp.highly_variable_genes(
                adata,
                n_top_genes=n_top_genes,
                batch_key=batch_key,
                flavor='seurat_v3',
                layer='counts' if 'counts' in adata.layers else None
            )

        n_hvgs = adata.var['highly_variable'].sum()
        print(f"  Highly variable genes: {n_hvgs}")

        if n_hvgs < 500:
            warnings.warn(
                f"Only {n_hvgs} HVGs found. Consider increasing n_top_genes or "
                "setting highly_variable_genes=False."
            )

    print("  Data preparation complete.\n")

    # Always return adata for convenience
    return adata


def _check_batch_condition_confounding(
    adata: sc.AnnData,
    batch_key: str,
    condition_key: Optional[str] = None
) -> None:
    """
    Check for batch-condition confounding and warn if detected.

    When a biological condition is represented by only one sample/batch,
    the condition effect is perfectly confounded with that sample's technical
    batch. Integration methods cannot distinguish biological signal from
    technical noise in this case.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    batch_key : str
        Column containing batch/sample labels
    condition_key : str, optional
        Column containing condition labels (e.g., 'condition', 'disease').
        If None, attempts to auto-detect from common column names.
    """
    # Try to auto-detect condition column
    if condition_key is None:
        candidate_keys = ['condition', 'disease', 'group', 'treatment',
                          'status', 'diagnosis', 'phenotype']
        for key in candidate_keys:
            if key in adata.obs.columns:
                condition_key = key
                break
        if condition_key is None:
            return  # No condition column found; skip check

    if condition_key not in adata.obs.columns:
        return

    # Count samples per condition
    batch_condition = adata.obs[[batch_key, condition_key]].drop_duplicates()
    condition_counts = batch_condition[condition_key].value_counts()

    singleton_conditions = condition_counts[condition_counts == 1]
    if len(singleton_conditions) > 0:
        print(f"\n  [WARNING] BATCH-CONDITION CONFOUNDING:")
        print(f"     The following condition(s) have only 1 sample:")
        for cond, count in singleton_conditions.items():
            sample = batch_condition.loc[
                batch_condition[condition_key] == cond, batch_key
            ].values[0]
            print(f"       '{cond}': 1 sample ({sample})")
        print(f"     When a condition has N=1, its biological signal is confounded")
        print(f"     with that sample's technical batch. scVI will model batch effects")
        print(f"     across samples, which may partially absorb real biological differences.")
        print(f"     Interpretation notes:")
        print(f"       - Clustering and cell type annotation remain valid")
        print(f"       - Cell composition differences should be interpreted with caution")
        print(f"       - Pseudobulk DE requires ≥2 replicates per condition (N=1 is invalid)")
        print(f"       - scVI's partial mixing (iLISI < max) is expected and appropriate here")
    else:
        min_count = condition_counts.min()
        if min_count < 3:
            print(f"\n  [INFO] Note: Some conditions have only {min_count} samples.")
            print(f"     Condition distribution: {dict(condition_counts)}")
            print(f"     Minimum 3 per condition recommended for downstream pseudobulk DE.")


def run_scvi_integration(
    adata: sc.AnnData,
    batch_key: str,
    condition_key: Optional[str] = None,
    n_latent: int = 30,
    n_layers: int = 2,
    n_hidden: int = 128,
    max_epochs: int = 400,
    early_stopping: bool = True,
    use_gpu: bool = True,
    use_highly_variable: bool = True,
    save_model: Optional[Union[str, Path]] = None,
    random_state: int = 0
) -> sc.AnnData:
    """
    Run scVI integration for batch correction.

    scVI (single-cell Variational Inference) learns a low-dimensional latent
    representation of gene expression while explicitly modeling batch effects
    using a deep generative model.

    Parameters
    ----------
    adata : AnnData
        AnnData object with raw counts
    batch_key : str
        Column in adata.obs containing batch labels
    condition_key : str, optional
        Column containing biological condition (e.g., 'condition', 'disease').
        Used to check for batch-condition confounding.
        If None, auto-detects from common column names.
    n_latent : int, optional
        Dimensionality of latent space (default: 30)
        Recommendation: 30 for complex data, 20 for simple
    n_layers : int, optional
        Number of hidden layers (default: 2)
    n_hidden : int, optional
        Number of nodes per hidden layer (default: 128)
    max_epochs : int, optional
        Maximum training epochs (default: 400)
    early_stopping : bool, optional
        Enable early stopping (default: True)
    use_gpu : bool, optional
        Use GPU for training (default: True, 10-20x faster)
    use_highly_variable : bool, optional
        Use only highly variable genes (default: True)
    save_model : str or Path, optional
        Directory to save trained model (default: None)
    random_state : int, optional
        Random seed for reproducibility (default: 0)

    Returns
    -------
    AnnData
        Input AnnData with integrated representation in .obsm['X_scvi']

    Notes
    -----
    Requires scvi-tools: pip install scvi-tools
    GPU highly recommended for reasonable runtime.

    Examples
    --------
    >>> adata = run_scvi_integration(adata, batch_key='batch', n_latent=30)
    >>> sc.pp.neighbors(adata, use_rep='X_scvi')
    >>> sc.tl.umap(adata)
    """
    try:
        import scvi
    except ImportError:
        raise ImportError(
            "scvi-tools is required for scVI integration.\n"
            "Install with: pip install scvi-tools"
        )

    print("=" * 60)
    print("scVI Integration")
    print("=" * 60)

    # Check for batch-condition confounding
    _check_batch_condition_confounding(adata, batch_key, condition_key)

    # Prepare data
    if use_highly_variable and 'highly_variable' in adata.var.columns:
        adata_input = adata[:, adata.var['highly_variable']].copy()
        print(f"Using {adata_input.n_vars} highly variable genes")
    else:
        adata_input = adata.copy()

    # Setup AnnData for scVI
    print("\nSetting up scVI model...")
    scvi.model.SCVI.setup_anndata(
        adata_input,
        batch_key=batch_key,
        layer='counts' if 'counts' in adata_input.layers else None
    )

    # Create model
    model = scvi.model.SCVI(
        adata_input,
        n_latent=n_latent,
        n_layers=n_layers,
        n_hidden=n_hidden,
        gene_likelihood='nb',
        dropout_rate=0.1
    )

    print(f"\nModel architecture:")
    print(f"  Latent dimensions: {n_latent}")
    print(f"  Hidden layers: {n_layers}")
    print(f"  Hidden layer size: {n_hidden}")
    print(f"  Gene likelihood: negative binomial")

    # Train model
    print(f"\nTraining scVI model...")
    print(f"  Max epochs: {max_epochs}")
    print(f"  Early stopping: {early_stopping}")
    print(f"  Using GPU: {use_gpu}")

    if use_gpu:
        try:
            import torch
            if not torch.cuda.is_available():
                print("  WARNING: GPU requested but CUDA not available. Using CPU.")
                use_gpu = False
        except ImportError:
            print("  WARNING: PyTorch not found. Using CPU.")
            use_gpu = False

    model.train(
        max_epochs=max_epochs,
        early_stopping=early_stopping,
        use_gpu=use_gpu,
        check_val_every_n_epoch=10,
        train_size=0.9
    )

    # Check convergence
    train_loss = model.history['elbo_train'][1:]
    val_loss = model.history['elbo_validation']

    print(f"\nTraining complete:")
    print(f"  Final train loss: {train_loss[-1]:.2f}")
    print(f"  Final validation loss: {val_loss[-1]:.2f}")
    print(f"  Epochs trained: {len(train_loss)}")

    # Get latent representation
    print("\nExtracting latent representation...")
    latent = model.get_latent_representation()

    # Add to original AnnData
    adata.obsm['X_scvi'] = latent

    print(f"  Added 'X_scvi' to adata.obsm (shape: {latent.shape})")

    # Save model if requested
    if save_model is not None:
        save_path = Path(save_model)
        save_path.mkdir(parents=True, exist_ok=True)
        model.save(save_path, overwrite=True)
        print(f"\nModel saved to: {save_path}")

    # Store integration info
    adata.uns['scvi_integration'] = {
        'batch_key': batch_key,
        'n_latent': n_latent,
        'n_layers': n_layers,
        'n_hidden': n_hidden,
        'max_epochs': max_epochs,
        'epochs_trained': len(train_loss),
        'final_train_loss': float(train_loss[-1]),
        'final_val_loss': float(val_loss[-1]),
        'use_highly_variable': use_highly_variable,
        'n_genes': adata_input.n_vars
    }

    print("\n" + "=" * 60)
    print("scVI integration complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  sc.pp.neighbors(adata, use_rep='X_scvi')")
    print("  sc.tl.umap(adata)")
    print("  sc.pl.umap(adata, color=['batch', 'cell_type'])")

    return adata


def run_scanvi_integration(
    adata: sc.AnnData,
    batch_key: str,
    labels_key: str,
    unlabeled_category: str = "Unknown",
    from_scvi_model: Optional[str] = None,
    n_latent: int = 30,
    n_layers: int = 2,
    n_hidden: int = 128,
    max_epochs: int = 200,
    use_gpu: bool = True,
    use_highly_variable: bool = True,
    save_model: Optional[Union[str, Path]] = None,
    random_state: int = 0
) -> sc.AnnData:
    """
    Run scANVI integration with semi-supervised learning.

    scANVI extends scVI by incorporating cell type labels during training,
    improving integration quality especially for rare cell types.

    Parameters
    ----------
    adata : AnnData
        AnnData object with raw counts
    batch_key : str
        Column in adata.obs containing batch labels
    labels_key : str
        Column in adata.obs containing cell type labels
        Can include unlabeled cells (use unlabeled_category)
    unlabeled_category : str, optional
        Label for unlabeled cells (default: "Unknown")
    from_scvi_model : str or Path, optional
        Path to pre-trained scVI model (recommended approach)
        If None, trains scANVI from scratch
    n_latent : int, optional
        Latent dimensions (default: 30)
    n_layers : int, optional
        Hidden layers (default: 2)
    n_hidden : int, optional
        Hidden layer size (default: 128)
    max_epochs : int, optional
        Training epochs (default: 200)
    use_gpu : bool, optional
        Use GPU (default: True)
    use_highly_variable : bool, optional
        Use HVGs only (default: True)
    save_model : str or Path, optional
        Directory to save model (default: None)
    random_state : int, optional
        Random seed (default: 0)

    Returns
    -------
    AnnData
        Input AnnData with:
        - .obsm['X_scanvi']: Integrated representation
        - .obs['scanvi_predictions']: Predicted cell types

    Notes
    -----
    Best practice: Train scVI first, then initialize scANVI from it.

    Examples
    --------
    >>> # Option 1: From scratch
    >>> adata = run_scanvi_integration(
    ...     adata, batch_key='batch', labels_key='cell_type'
    ... )
    >>>
    >>> # Option 2: From pre-trained scVI (recommended)
    >>> adata = run_scvi_integration(adata, 'batch', save_model='scvi_model/')
    >>> adata = run_scanvi_integration(
    ...     adata, 'batch', 'cell_type', from_scvi_model='scvi_model/'
    ... )
    """
    try:
        import scvi
    except ImportError:
        raise ImportError(
            "scvi-tools is required for scANVI integration.\n"
            "Install with: pip install scvi-tools"
        )

    print("=" * 60)
    print("scANVI Integration")
    print("=" * 60)

    # Check labels column
    if labels_key not in adata.obs.columns:
        raise ValueError(f"Labels key '{labels_key}' not found in adata.obs")

    n_labeled = (adata.obs[labels_key] != unlabeled_category).sum()
    n_unlabeled = (adata.obs[labels_key] == unlabeled_category).sum()
    n_categories = adata.obs[labels_key].nunique()

    print(f"\nLabel information:")
    print(f"  Labeled cells: {n_labeled} ({100*n_labeled/adata.n_obs:.1f}%)")
    print(f"  Unlabeled cells: {n_unlabeled} ({100*n_unlabeled/adata.n_obs:.1f}%)")
    print(f"  Cell type categories: {n_categories}")

    # Prepare data
    if use_highly_variable and 'highly_variable' in adata.var.columns:
        adata_input = adata[:, adata.var['highly_variable']].copy()
        print(f"  Using {adata_input.n_vars} highly variable genes")
    else:
        adata_input = adata.copy()

    # Option 1: Initialize from pre-trained scVI model (recommended)
    if from_scvi_model is not None:
        print(f"\nLoading pre-trained scVI model from: {from_scvi_model}")

        # Load scVI model
        scvi_model = scvi.model.SCVI.load(from_scvi_model, adata_input)

        # Setup for scANVI
        print("Setting up scANVI from scVI model...")
        scvi.model.SCANVI.setup_anndata(
            adata_input,
            batch_key=batch_key,
            labels_key=labels_key,
            unlabeled_category=unlabeled_category,
            layer='counts' if 'counts' in adata_input.layers else None
        )

        # Create scANVI model from scVI
        model = scvi.model.SCANVI.from_scvi_model(
            scvi_model,
            unlabeled_category=unlabeled_category,
            labels_key=labels_key
        )

        print("  scANVI initialized from pre-trained scVI model")

    # Option 2: Train scANVI from scratch
    else:
        print("\nTraining scANVI from scratch...")
        print("  Recommendation: Train scVI first for better results")

        # Setup AnnData
        scvi.model.SCANVI.setup_anndata(
            adata_input,
            batch_key=batch_key,
            labels_key=labels_key,
            unlabeled_category=unlabeled_category,
            layer='counts' if 'counts' in adata_input.layers else None
        )

        # Create model
        model = scvi.model.SCANVI(
            adata_input,
            n_latent=n_latent,
            n_layers=n_layers,
            n_hidden=n_hidden,
            unlabeled_category=unlabeled_category
        )

    # Train model
    print(f"\nTraining scANVI model...")
    print(f"  Max epochs: {max_epochs}")
    print(f"  Using GPU: {use_gpu}")

    if use_gpu:
        try:
            import torch
            if not torch.cuda.is_available():
                print("  WARNING: GPU requested but CUDA not available. Using CPU.")
                use_gpu = False
        except ImportError:
            print("  WARNING: PyTorch not found. Using CPU.")
            use_gpu = False

    model.train(
        max_epochs=max_epochs,
        use_gpu=use_gpu,
        check_val_every_n_epoch=10,
        train_size=0.9
    )

    print("\nTraining complete")

    # Get latent representation
    print("\nExtracting latent representation and predictions...")
    latent = model.get_latent_representation()
    predictions = model.predict()

    # Add to original AnnData
    adata.obsm['X_scanvi'] = latent
    adata.obs['scanvi_predictions'] = predictions

    print(f"  Added 'X_scanvi' to adata.obsm (shape: {latent.shape})")
    print(f"  Added 'scanvi_predictions' to adata.obs")

    # Prediction accuracy for labeled cells
    if n_labeled > 0:
        labeled_mask = adata.obs[labels_key] != unlabeled_category
        true_labels = adata.obs.loc[labeled_mask, labels_key]
        pred_labels = adata.obs.loc[labeled_mask, 'scanvi_predictions']
        accuracy = (true_labels == pred_labels).mean()
        print(f"\n  Prediction accuracy on labeled cells: {accuracy:.1%}")

    # Save model if requested
    if save_model is not None:
        save_path = Path(save_model)
        save_path.mkdir(parents=True, exist_ok=True)
        model.save(save_path, overwrite=True)
        print(f"\nModel saved to: {save_path}")

    # Store integration info
    adata.uns['scanvi_integration'] = {
        'batch_key': batch_key,
        'labels_key': labels_key,
        'unlabeled_category': unlabeled_category,
        'n_labeled': int(n_labeled),
        'n_unlabeled': int(n_unlabeled),
        'n_categories': int(n_categories),
        'from_scvi': from_scvi_model is not None,
        'use_highly_variable': use_highly_variable,
        'n_genes': adata_input.n_vars
    }

    print("\n" + "=" * 60)
    print("scANVI integration complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  sc.pp.neighbors(adata, use_rep='X_scanvi')")
    print("  sc.tl.umap(adata)")
    print("  sc.pl.umap(adata, color=['batch', 'scanvi_predictions'])")

    return adata


def run_harmony_integration(
    adata: sc.AnnData,
    batch_key: str,
    theta: float = 2.0,
    max_iter_harmony: int = 10,
    use_pca: bool = True,
    n_pcs: int = 50,
    random_state: int = 0
) -> sc.AnnData:
    """
    Run Harmony integration for fast batch correction.

    Harmony is a fast, interpretable integration method that iteratively
    clusters and corrects PCA space.

    Parameters
    ----------
    adata : AnnData
        AnnData object (normalized data in .X or .layers)
    batch_key : str
        Column in adata.obs containing batch labels
    theta : float, optional
        Diversity penalty (default: 2.0)
        - 0: No correction
        - 1: Gentle correction
        - 2: Standard correction (recommended)
        - 4: Aggressive correction
    max_iter_harmony : int, optional
        Number of Harmony iterations (default: 10)
    use_pca : bool, optional
        Run PCA before Harmony (default: True)
        If False, uses existing adata.obsm['X_pca']
    n_pcs : int, optional
        Number of PCs to compute/use (default: 50)
    random_state : int, optional
        Random seed (default: 0)

    Returns
    -------
    AnnData
        Input AnnData with integrated representation in .obsm['X_harmony']

    Notes
    -----
    Requires harmonypy: pip install harmonypy
    Very fast (minutes even for large datasets), no GPU needed.

    Examples
    --------
    >>> adata = run_harmony_integration(adata, batch_key='batch', theta=2)
    >>> sc.pp.neighbors(adata, use_rep='X_harmony')
    >>> sc.tl.umap(adata)
    """
    try:
        import harmonypy as hm
    except ImportError:
        raise ImportError(
            "harmonypy is required for Harmony integration.\n"
            "Install with: pip install harmonypy"
        )

    print("=" * 60)
    print("Harmony Integration")
    print("=" * 60)

    # Check batch column
    if batch_key not in adata.obs.columns:
        raise ValueError(f"Batch key '{batch_key}' not found in adata.obs")

    n_batches = adata.obs[batch_key].nunique()
    print(f"\nBatch information:")
    print(f"  Batches: {n_batches} ({batch_key})")
    print(f"  Cells: {adata.n_obs}")

    # Run PCA if needed
    if use_pca or 'X_pca' not in adata.obsm:
        print(f"\nComputing PCA with {n_pcs} components...")
        sc.tl.pca(adata, n_comps=n_pcs, random_state=random_state)
    else:
        print(f"\nUsing existing PCA from adata.obsm['X_pca']")
        n_pcs = adata.obsm['X_pca'].shape[1]

    print(f"  PCA shape: {adata.obsm['X_pca'].shape}")

    # Run Harmony
    print(f"\nRunning Harmony integration...")
    print(f"  Theta (diversity penalty): {theta}")
    print(f"  Max iterations: {max_iter_harmony}")

    harmony_out = hm.run_harmony(
        adata.obsm['X_pca'],
        adata.obs,
        batch_key,
        theta=theta,
        max_iter_harmony=max_iter_harmony,
        random_state=random_state,
        verbose=False
    )

    # Add to AnnData
    adata.obsm['X_harmony'] = harmony_out.Z_corr.T

    print(f"\n  Added 'X_harmony' to adata.obsm (shape: {adata.obsm['X_harmony'].shape})")

    # Store integration info
    adata.uns['harmony_integration'] = {
        'batch_key': batch_key,
        'theta': theta,
        'max_iter_harmony': max_iter_harmony,
        'n_pcs': n_pcs,
        'n_batches': int(n_batches)
    }

    print("\n" + "=" * 60)
    print("Harmony integration complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  sc.pp.neighbors(adata, use_rep='X_harmony')")
    print("  sc.tl.umap(adata)")
    print("  sc.pl.umap(adata, color=['batch', 'cell_type'])")

    return adata


# Example usage
if __name__ == "__main__":
    print("Example Harmony integration workflow:")
    print("  adata = setup_for_integration(adata, batch_key='batch')")
    print("  adata = run_harmony_integration(adata, batch_key='batch', theta=2)")
    print("  sc.pp.neighbors(adata, use_rep='X_harmony')")
    print("  sc.tl.umap(adata)")
    print()
    print("Example scVI integration workflow:")
    print("  adata = setup_for_integration(adata, batch_key='batch')")
    print("  adata = run_scvi_integration(adata, batch_key='batch', n_latent=30)")
    print("  sc.pp.neighbors(adata, use_rep='X_scvi')")
    print("  sc.tl.umap(adata)")
    print()
    print("Example scANVI integration workflow:")
    print("  adata = run_scvi_integration(adata, 'batch', save_model='scvi_model/')")
    print("  adata = run_scanvi_integration(adata, 'batch', 'cell_type', from_scvi_model='scvi_model/')")
    print("  sc.pp.neighbors(adata, use_rep='X_scanvi')")
    print("  sc.tl.umap(adata)")

