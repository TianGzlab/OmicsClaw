"""ComBat computations and temporary R execution."""
from __future__ import annotations
import logging
from pathlib import Path
import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)

def _combat_correct(data: pd.DataFrame, batch_labels: pd.Series) -> pd.DataFrame:
    """Parametric ComBat batch correction (Johnson et al., 2007).

    Parameters
    ----------
    data : DataFrame
        Genes-as-rows, samples-as-columns expression matrix.
    batch_labels : Series
        Batch label for each sample (index must match data.columns).

    Returns
    -------
    Corrected DataFrame of same shape.
    """
    dat = data.values.astype(float).copy()
    n_genes, n_samples = dat.shape
    batches = batch_labels.values
    unique_batches = np.unique(batches)
    n_batch = len(unique_batches)

    if n_batch < 2:
        logger.warning("Only 1 batch detected; returning data unchanged.")
        return data.copy()

    # Batch indices
    batch_idx = {b: np.where(batches == b)[0] for b in unique_batches}
    n_per_batch = {b: len(idx) for b, idx in batch_idx.items()}

    # Step 1: Standardize per gene
    grand_mean = dat.mean(axis=1)
    grand_var = dat.var(axis=1, ddof=1)
    grand_var[grand_var == 0] = 1e-10

    # Design matrix for batches
    stand_data = (dat - grand_mean[:, None]) / np.sqrt(grand_var[:, None])

    # Step 2: Estimate batch parameters (location gamma, scale delta^2)
    gamma_hat = np.zeros((n_batch, n_genes))
    delta_hat_sq = np.zeros((n_batch, n_genes))
    for i, b in enumerate(unique_batches):
        idx = batch_idx[b]
        gamma_hat[i] = stand_data[:, idx].mean(axis=1)
        delta_hat_sq[i] = stand_data[:, idx].var(axis=1, ddof=1)
        delta_hat_sq[i][delta_hat_sq[i] == 0] = 1e-10

    # Step 3: Empirical Bayes shrinkage (parametric)
    gamma_bar = gamma_hat.mean(axis=1)
    tau_sq = gamma_hat.var(axis=1, ddof=1)
    tau_sq[tau_sq == 0] = 1e-10

    # For delta: use inverse-gamma prior
    m_bar = delta_hat_sq.mean(axis=1)
    s_sq = delta_hat_sq.var(axis=1, ddof=1)
    s_sq[s_sq == 0] = 1e-10

    gamma_star = np.zeros_like(gamma_hat)
    delta_star_sq = np.zeros_like(delta_hat_sq)

    for i in range(n_batch):
        n_b = n_per_batch[unique_batches[i]]
        # Posterior for gamma (normal prior)
        gamma_star[i] = (n_b * tau_sq[i] * gamma_hat[i] + delta_hat_sq[i] * gamma_bar[i]) / \
                        (n_b * tau_sq[i] + delta_hat_sq[i])
        # Posterior for delta_sq (inverse-gamma prior)
        # Use shrinkage toward the grand mean
        lambda_b = (m_bar[i] ** 2 + 2 * s_sq[i]) / s_sq[i]
        theta_b = (m_bar[i] ** 3 + m_bar[i] * s_sq[i]) / s_sq[i]
        theta_b = np.where(theta_b == 0, 1e-10, theta_b)
        delta_star_sq[i] = (theta_b + 0.5 * n_b * delta_hat_sq[i]) / \
                           (lambda_b / 2 + n_b / 2 - 1)
        delta_star_sq[i] = np.maximum(delta_star_sq[i], 1e-10)

    # Step 4: Adjust data
    corrected = dat.copy()
    for i, b in enumerate(unique_batches):
        idx = batch_idx[b]
        dsq = np.sqrt(delta_star_sq[i])
        dsq[dsq == 0] = 1e-10
        corrected[:, idx] = grand_mean[:, None] + np.sqrt(grand_var[:, None]) * \
            (stand_data[:, idx] - gamma_star[i][:, None]) / dsq[:, None]

    return pd.DataFrame(corrected, index=data.index, columns=data.columns)

def _run_pca(data: pd.DataFrame, n_components: int = 2) -> np.ndarray:
    """Simple PCA via SVD on centered data (genes x samples -> samples in PC space)."""
    values = data.to_numpy(dtype=float)
    log_data = np.sign(values) * np.log2(np.abs(values) + 1)
    centered = log_data - log_data.mean(axis=1, keepdims=True)
    U, S, Vt = np.linalg.svd(centered.T, full_matrices=False)
    return U[:, :n_components] * S[:n_components]

def _silhouette_score(pc_coords: np.ndarray, labels: np.ndarray) -> float:
    """Compute silhouette score (simplified). Higher = more separated batches."""
    from scipy.spatial.distance import cdist
    unique = np.unique(labels)
    if len(unique) < 2:
        return 0.0
    dists = cdist(pc_coords, pc_coords, metric='euclidean')
    n = len(labels)
    sil = np.zeros(n)
    for i in range(n):
        same = labels == labels[i]
        diff_labels = unique[unique != labels[i]]
        a_i = dists[i, same].sum() / max(same.sum() - 1, 1)
        b_i = min(dists[i, labels == dl].mean() for dl in diff_labels)
        sil[i] = (b_i - a_i) / max(a_i, b_i, 1e-10)
    return float(np.mean(sil))
