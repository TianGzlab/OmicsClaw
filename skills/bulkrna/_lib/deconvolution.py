"""NNLS cell-mixture estimation shared by bulk entry points."""
import logging
import numpy as np
import pandas as pd
from scipy.optimize import nnls
logger = logging.getLogger(__name__)

def _run_nnls(mixture: np.ndarray, signature: np.ndarray) -> np.ndarray:
    """Run NNLS for a single sample and normalize to proportions.

    Parameters
    ----------
    mixture : 1-D array of expression values for one sample.
    signature : 2-D array (genes x cell_types).

    Returns
    -------
    Proportions array summing to 1.
    """
    coeffs, residual = nnls(signature, mixture)
    total = coeffs.sum()
    if total > 0:
        coeffs = coeffs / total
    return coeffs

def core_analysis(
    counts: pd.DataFrame,
    signature: pd.DataFrame,
) -> dict:
    """Deconvolve every sample via NNLS.

    Parameters
    ----------
    counts : DataFrame with genes as rows and samples as columns.
    signature : DataFrame with genes as rows and cell types as columns.

    Returns
    -------
    Summary dict with proportions, dominant types, mean proportions, etc.
    """
    shared_genes = sorted(set(counts.index) & set(signature.index))
    if not shared_genes:
        raise ValueError(
            "No shared genes between count matrix and signature matrix. "
            "Check that both use the same gene identifier format."
        )
    logger.info("Shared genes: %d", len(shared_genes))

    sig_mat = signature.loc[shared_genes].values.astype(float)
    cell_types = list(signature.columns)
    samples = list(counts.columns)

    proportions = np.zeros((len(samples), len(cell_types)))
    residuals = np.zeros(len(samples))

    for i, sample in enumerate(samples):
        mix = counts.loc[shared_genes, sample].values.astype(float)
        # Run raw NNLS (before normalizing to proportions) for residual
        raw_coeffs, _ = nnls(sig_mat, mix)
        total = raw_coeffs.sum()
        if total <= 0:
            raise ValueError(f'Sample {sample!r} has no supported signal in shared reference genes')
        proportions[i] = raw_coeffs / total
        # Reconstruction residual: RMSE between raw mix and NNLS reconstruction
        reconstructed = sig_mat @ raw_coeffs
        residuals[i] = float(np.sqrt(np.mean((mix - reconstructed) ** 2)))

    proportions_df = pd.DataFrame(proportions, index=samples, columns=cell_types)
    proportions_df.index.name = "sample"

    # Dominant cell type per sample
    dominant_types = proportions_df.idxmax(axis=1).to_dict()

    # Mean proportions across all samples
    mean_proportions = proportions_df.mean(axis=0).to_dict()

    summary = {
        "n_genes_shared": len(shared_genes),
        "n_samples": len(samples),
        "n_cell_types": len(cell_types),
        "cell_types": cell_types,
        "proportions_df": proportions_df,
        "dominant_types": dominant_types,
        "mean_proportions": mean_proportions,
        "residuals": residuals.tolist(),
    }
    return summary
