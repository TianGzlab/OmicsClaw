"""NNLS and PCA/kNN calculations for bulk-reference placement."""
from __future__ import annotations
import numpy as np
import pandas as pd

def demo_data(*, random_state=42) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, np.ndarray]:
    """Generate demo bulk + scRNA-seq reference with trajectory.

    Returns: (bulk_counts, ref_counts, ref_celltypes, ref_pseudotime)
    """
    rng = np.random.RandomState(random_state)
    n_genes = 500
    n_bulk = 10
    n_cells = 800
    genes = [f"Gene_{i}" for i in range(n_genes)]
    cell_types = ["Progenitor", "Intermediate", "Mature_A", "Mature_B"]

    # Reference scRNA-seq: 4 cell types along a trajectory
    ref_data = np.zeros((n_cells, n_genes))
    ref_labels = []
    ref_pt = np.zeros(n_cells)

    cells_per_type = n_cells // len(cell_types)
    for ti, ct in enumerate(cell_types):
        idx = slice(ti * cells_per_type, (ti + 1) * cells_per_type)
        # Each cell type has different expression profiles
        base = rng.exponential(5, n_genes)
        # Cell-type specific marker genes (50 per type)
        markers = np.arange(ti * 50, (ti + 1) * 50) % n_genes
        base[markers] *= rng.uniform(5, 15)
        for j in range(cells_per_type):
            noise = rng.exponential(1, n_genes)
            ref_data[ti * cells_per_type + j] = base + noise
        ref_labels.extend([ct] * cells_per_type)
        # Pseudotime increases with cell type progression
        ref_pt[idx] = np.linspace(ti * 0.25, (ti + 1) * 0.25, cells_per_type) + \
                      rng.normal(0, 0.02, cells_per_type)

    ref_pt = np.clip(ref_pt, 0, 1)

    # Bulk data: mixtures of cell types
    bulk_data = np.zeros((n_bulk, n_genes))
    true_fractions = rng.dirichlet([2, 3, 4, 1], n_bulk)
    for i in range(n_bulk):
        for ti, ct in enumerate(cell_types):
            ct_mean = ref_data[ti * cells_per_type:(ti + 1) * cells_per_type].mean(axis=0)
            bulk_data[i] += true_fractions[i, ti] * ct_mean * rng.uniform(80, 120)
    bulk_data = np.round(bulk_data).astype(int)

    bulk_df = pd.DataFrame(bulk_data, columns=genes,
                           index=[f"BulkSample_{i}" for i in range(n_bulk)])
    ref_df = pd.DataFrame(ref_data, columns=genes,
                          index=[f"Cell_{i}" for i in range(n_cells)])

    return bulk_df, ref_df, pd.Series(ref_labels, index=ref_df.index), ref_pt


def estimate_fractions(bulk: pd.DataFrame, ref: pd.DataFrame,
                       ref_labels: pd.Series) -> pd.DataFrame:
    """Estimate cell type fractions via NNLS deconvolution."""
    from scipy.optimize import nnls
    cell_types = sorted(ref_labels.unique())

    # Build signature matrix: mean expression per cell type
    sig = pd.DataFrame(index=ref.columns)
    for ct in cell_types:
        ct_cells = ref_labels[ref_labels == ct].index
        sig[ct] = ref.loc[ct_cells].mean(axis=0)

    # Common genes
    common = bulk.columns.intersection(sig.index)
    if len(common) < 50:
        raise ValueError(f"Only {len(common)} common genes — need >= 50")

    S = sig.loc[common].values  # genes x cell_types
    fractions = {}
    for sample in bulk.index:
        b = bulk.loc[sample, common].values.astype(float)
        x, _ = nnls(S, b)
        x_norm = x / x.sum() if x.sum() > 0 else x
        fractions[sample] = dict(zip(cell_types, x_norm))

    return pd.DataFrame(fractions).T


def map_bulk_to_trajectory(bulk: pd.DataFrame, ref: pd.DataFrame,
                           ref_pseudotime: np.ndarray,
                           k: int = 15, random_state: int = 42) -> pd.DataFrame:
    """Map bulk samples onto reference trajectory via PCA + KNN."""
    from sklearn.decomposition import PCA
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler
    common = bulk.columns.intersection(ref.columns)

    combined = pd.concat([ref[common], bulk[common]], axis=0)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(np.log1p(combined.values))

    pca = PCA(n_components=min(20, scaled.shape[1], scaled.shape[0]), random_state=random_state)
    pcs = pca.fit_transform(scaled)

    n_ref = ref.shape[0]
    ref_pcs = pcs[:n_ref]
    bulk_pcs = pcs[n_ref:]

    # KNN mapping
    nn = NearestNeighbors(n_neighbors=k, metric="euclidean")
    nn.fit(ref_pcs)
    dists, indices = nn.kneighbors(bulk_pcs)

    results = []
    for i, sample in enumerate(bulk.index):
        neighbor_pts = ref_pseudotime[indices[i]]
        mean_pt = float(np.mean(neighbor_pts))
        std_pt = float(np.std(neighbor_pts))
        results.append({
            "sample": sample,
            "pseudotime": round(mean_pt, 4),
            "pseudotime_std": round(std_pt, 4),
            "mean_neighbor_dist": round(float(np.mean(dists[i])), 4),
            "pc1": float(bulk_pcs[i, 0]),
            "pc2": float(bulk_pcs[i, 1]),
        })

    return pd.DataFrame(results).set_index("sample"), ref_pcs, bulk_pcs, pca
