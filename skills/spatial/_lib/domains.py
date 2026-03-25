"""Spatial domain identification algorithms.

Provides multiple methods for tissue region/niche identification:
  - leiden:   Graph-based clustering with spatial-weighted neighbors (default)
  - louvain:  Classic graph-based clustering
  - spagcn:   Spatial Graph Convolutional Network
  - stagate:  Graph attention auto-encoder (PyTorch Geometric)
  - graphst:  Self-supervised contrastive learning (PyTorch)
  - banksy:   Explicit spatial feature augmentation

Usage::

    from skills.spatial._lib.domains import (
        identify_domains_leiden,
        identify_domains_spagcn,
        refine_spatial_domains,
        SUPPORTED_METHODS,
    )

    summary = identify_domains_leiden(adata, resolution=1.0)
"""

from __future__ import annotations

import logging
from collections import Counter

import numpy as np
import pandas as pd
import scanpy as sc

from .adata_utils import ensure_neighbors, ensure_pca, get_spatial_key, require_spatial_coords

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("leiden", "louvain", "spagcn", "stagate", "graphst", "banksy")


# ---------------------------------------------------------------------------
# Spatial domain refinement (shared across methods)
# ---------------------------------------------------------------------------


def refine_spatial_domains(
    adata,
    domain_key: str = "spatial_domain",
    *,
    threshold: float = 0.5,
    k: int = 10,
) -> pd.Series:
    """Spatially smooth domain labels using k-nearest neighbor majority vote.

    Only relabels a spot when >threshold fraction of its neighbors disagree,
    following the approach from Hu et al., Nature Methods 2021 (SpaGCN).
    """
    from sklearn.neighbors import NearestNeighbors

    spatial_key = get_spatial_key(adata)
    if spatial_key is None:
        return adata.obs[domain_key]

    coords = adata.obsm[spatial_key]
    labels = adata.obs[domain_key].values.astype(str)

    k = min(k, len(labels) - 1)
    if k < 1:
        return pd.Series(labels, index=adata.obs.index)

    nbrs = NearestNeighbors(n_neighbors=k).fit(coords)
    _, indices = nbrs.kneighbors(coords)

    refined = []
    for i, neighbors in enumerate(indices):
        neighbor_labels = labels[neighbors]
        different_ratio = np.sum(neighbor_labels != labels[i]) / len(neighbor_labels)
        if different_ratio >= threshold:
            most_common = Counter(neighbor_labels).most_common(1)[0][0]
            refined.append(most_common)
        else:
            refined.append(labels[i])

    return pd.Series(refined, index=adata.obs.index)


# ---------------------------------------------------------------------------
# Domain identification methods
# ---------------------------------------------------------------------------


def identify_domains_leiden(
    adata,
    *,
    resolution: float = 1.0,
    n_neighbors: int = 15,
    n_pcs: int = 50,
    spatial_weight: float = 0.3,
) -> dict:
    """Leiden clustering on a composite expression + spatial graph.

    When spatial coordinates are available, the expression-based and
    spatial-based neighbor graphs are combined with configurable weighting
    (following ChatSpatial's approach).
    """
    ensure_pca(adata, n_comps=n_pcs)
    ensure_neighbors(adata, n_neighbors=n_neighbors, n_pcs=min(n_pcs, 30))

    spatial_key = get_spatial_key(adata)
    if spatial_key is not None and spatial_weight > 0:
        try:
            import squidpy as sq
            sq.gr.spatial_neighbors(adata, spatial_key=spatial_key, coord_type="generic")
            if "spatial_connectivities" in adata.obsp:
                expr_w = 1 - spatial_weight
                combined = (
                    expr_w * adata.obsp["connectivities"]
                    + spatial_weight * adata.obsp["spatial_connectivities"]
                )
                adata.obsp["connectivities"] = combined
                logger.info(
                    "Combined expression (%.0f%%) + spatial (%.0f%%) graphs",
                    expr_w * 100, spatial_weight * 100,
                )
        except Exception as e:
            logger.warning("Could not build spatial graph, using expression only: %s", e)

    sc.tl.leiden(adata, resolution=resolution, flavor="igraph", key_added="spatial_domain")

    n_domains = adata.obs["spatial_domain"].nunique()
    logger.info("Leiden domains: %d (resolution=%.2f)", n_domains, resolution)

    return {
        "method": "leiden",
        "n_domains": n_domains,
        "resolution": resolution,
        "spatial_weight": spatial_weight if spatial_key else 0.0,
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def identify_domains_louvain(
    adata,
    *,
    resolution: float = 1.0,
    n_neighbors: int = 15,
    n_pcs: int = 50,
) -> dict:
    """Louvain graph clustering for spatial domain identification.

    Requires the ``louvain`` Python package::

        pip install louvain
    """
    ensure_pca(adata, n_comps=n_pcs)
    ensure_neighbors(adata, n_neighbors=n_neighbors, n_pcs=min(n_pcs, 30))

    try:
        import louvain as _  # noqa: F401
    except ImportError:
        raise ImportError(
            "'louvain' is not installed.\n\n"
            "Install:     pip install louvain\n"
            "Alternative: use --method leiden (bundled with scanpy/leidenalg)"
        )

    sc.tl.louvain(adata, resolution=resolution, key_added="spatial_domain")

    n_domains = adata.obs["spatial_domain"].nunique()
    logger.info("Louvain domains: %d (resolution=%.2f)", n_domains, resolution)

    return {
        "method": "louvain",
        "n_domains": n_domains,
        "resolution": resolution,
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def identify_domains_spagcn(
    adata,
    *,
    n_domains: int = 7,
) -> dict:
    """SpaGCN — Spatial Graph Convolutional Network for domain identification."""
    from .dependency_manager import require

    require("SpaGCN", feature="SpaGCN spatial domain detection")

    import scipy.sparse
    import SpaGCN

    # SpaGCN 1.2.7 uses .A (removed in scipy >= 1.14); patch for compatibility
    if not hasattr(scipy.sparse.csr_matrix, "A"):
        scipy.sparse.csr_matrix.A = property(lambda self: self.toarray())

    spatial_key = require_spatial_coords(adata)
    coords = adata.obsm[spatial_key]

    x_pixel = coords[:, 0].astype(float)
    y_pixel = coords[:, 1].astype(float)

    logger.info("Building SpaGCN adjacency matrix ...")
    adj = SpaGCN.calculate_adj_matrix(x=x_pixel, y=y_pixel, histology=False)

    l_value = SpaGCN.search_l(0.5, adj, start=0.01, end=1000, tol=0.01, max_run=100)

    clf = SpaGCN.SpaGCN()
    clf.set_l(l_value)
    clf.train(
        adata, adj,
        num_pcs=50, init_spa=True, init="louvain",
        res=0.4, tol=5e-3, lr=0.05, max_epochs=200,
        n_clusters=n_domains,
    )

    y_pred, prob = clf.predict()
    adata.obs["spatial_domain"] = pd.Categorical(y_pred.astype(str))

    refined = SpaGCN.refine(
        sample_id=adata.obs.index.tolist(),
        pred=y_pred, dis=adj, shape="hexagon",
    )
    adata.obs["spatial_domain"] = pd.Categorical([str(r) for r in refined])

    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("SpaGCN domains: %d (requested %d)", actual_n, n_domains)

    return {
        "method": "spagcn",
        "n_domains": actual_n,
        "n_domains_requested": n_domains,
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def identify_domains_stagate(
    adata,
    *,
    n_domains: int = 7,
    rad_cutoff: float = 50.0,
    random_seed: int = 42,
) -> dict:
    """STAGATE — graph attention auto-encoder for spatial domain identification.

    Learns embeddings by integrating gene expression with spatial information
    through a graph attention mechanism. Requires STAGATE_pyG and PyTorch.
    """
    from .dependency_manager import require

    require("STAGATE_pyG", feature="STAGATE spatial domain identification")
    require("torch", feature="STAGATE (PyTorch backend)")

    import torch
    import STAGATE_pyG

    logger.info("Running STAGATE (rad_cutoff=%.1f, n_domains=%d) ...", rad_cutoff, n_domains)

    if "highly_variable" in adata.var.columns:
        n_hvg = adata.var["highly_variable"].sum()
        logger.info("Subsetting to %d HVGs for STAGATE autoencoder", n_hvg)
        adata_work = adata[:, adata.var["highly_variable"]].copy()
    else:
        logger.warning(
            "No 'highly_variable' annotation found; using all %d genes. "
            "Consider running sc.pp.highly_variable_genes() first for best results.",
            adata.n_vars,
        )
        adata_work = adata.copy()

    STAGATE_pyG.Cal_Spatial_Net(adata_work, rad_cutoff=rad_cutoff)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("STAGATE device: %s", device)

    adata_work = STAGATE_pyG.train_STAGATE(adata_work, device=device)

    from sklearn.mixture import GaussianMixture
    from sklearn.cluster import KMeans

    embedding = adata_work.obsm["STAGATE"]
    try:
        gmm = GaussianMixture(
            n_components=n_domains, covariance_type="tied",
            random_state=random_seed, reg_covar=1e-4,
        )
        labels = gmm.fit_predict(embedding)
        clustering_name = "gmm_tied"
    except Exception as e:
        logger.warning("GMM failed (%s), falling back to KMeans", e)
        kmeans = KMeans(n_clusters=n_domains, random_state=random_seed, n_init=10)
        labels = kmeans.fit_predict(embedding)
        clustering_name = "kmeans"

    adata.obs["spatial_domain"] = pd.Categorical(labels.astype(str))
    adata.obsm["X_stagate"] = embedding

    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("STAGATE domains: %d (requested %d)", actual_n, n_domains)

    return {
        "method": "stagate",
        "n_domains": actual_n,
        "n_domains_requested": n_domains,
        "rad_cutoff": rad_cutoff,
        "clustering": clustering_name,
        "device": str(device),
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def identify_domains_graphst(
    adata,
    *,
    n_domains: int = 7,
    random_seed: int = 0,
) -> dict:
    """GraphST — self-supervised contrastive learning for spatial domains.

    Important: GraphST.preprocess() internally performs log1p + normalize +
    scale + HVG selection. If adata.X is already log-normalized, raw counts
    are restored from adata.raw to avoid double log-transform.
    """
    from .dependency_manager import require

    require("GraphST", feature="GraphST spatial domain identification")
    require("torch", feature="GraphST (PyTorch backend)")

    import torch
    from GraphST import GraphST as GraphSTModule

    logger.info("Running GraphST (n_domains=%d) ...", n_domains)

    if adata.raw is not None:
        logger.info(
            "Restoring raw counts from adata.raw for GraphST "
            "(avoids double log-transform)"
        )
        adata_work = adata.raw.to_adata().copy()
        spatial_key = get_spatial_key(adata)
        if spatial_key and spatial_key in adata.obsm:
            adata_work.obsm[spatial_key] = adata.obsm[spatial_key]
        if "spatial" not in adata_work.obsm and spatial_key and spatial_key != "spatial":
            adata_work.obsm["spatial"] = adata.obsm[spatial_key]
    else:
        logger.warning(
            "adata.raw not found — using adata.X directly. If adata.X is "
            "already log-normalized, GraphST results may be suboptimal."
        )
        adata_work = adata.copy()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    GraphSTModule.preprocess(adata_work)
    GraphSTModule.construct_interaction(adata_work)

    from GraphST.GraphST import GraphST as GraphSTModel

    model = GraphSTModel(adata_work, device=device, random_seed=random_seed)
    adata_work = model.train()

    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture
    from sklearn.cluster import KMeans

    pca = PCA(n_components=20, random_state=42)
    embedding = pca.fit_transform(adata_work.obsm["emb"])

    try:
        gmm = GaussianMixture(
            n_components=n_domains, covariance_type="tied",
            random_state=random_seed, reg_covar=1e-4,
        )
        labels = gmm.fit_predict(embedding)
        clustering_name = "gmm_tied"
    except Exception as e:
        logger.warning("GMM failed (%s), falling back to KMeans", e)
        kmeans = KMeans(n_clusters=n_domains, random_state=random_seed, n_init=10)
        labels = kmeans.fit_predict(embedding)
        clustering_name = "kmeans"

    adata.obs["spatial_domain"] = pd.Categorical(labels.astype(str))
    adata.obsm["X_graphst"] = adata_work.obsm["emb"]

    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("GraphST domains: %d (requested %d)", actual_n, n_domains)

    return {
        "method": "graphst",
        "n_domains": actual_n,
        "n_domains_requested": n_domains,
        "clustering": clustering_name,
        "device": str(device),
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def identify_domains_banksy(
    adata,
    *,
    n_domains: int | None = None,
    resolution: float = 0.7,
    lambda_param: float = 0.2,
    num_neighbours: int = 15,
    max_m: int = 1,
    pca_dims: int = 20,
) -> dict:
    """BANKSY — spatial feature augmentation for domain identification.

    Augments gene expression with neighborhood-averaged expression and
    azimuthal Gabor filters. Applies sc.pp.scale() before BANKSY as
    recommended by the official tutorial.
    """
    from .dependency_manager import require

    require("banksy", feature="BANKSY spatial domain identification")

    from banksy.embed_banksy import generate_banksy_matrix
    from banksy.initialize_banksy import initialize_banksy

    logger.info("Running BANKSY (lambda=%.2f, resolution=%.2f) ...", lambda_param, resolution)

    adata_work = adata.copy()

    spatial_key = get_spatial_key(adata_work)
    if spatial_key is None:
        raise ValueError("BANKSY requires spatial coordinates in obsm")
    if spatial_key != "spatial":
        adata_work.obsm["spatial"] = adata_work.obsm[spatial_key]

    logger.info("Applying z-score scaling before BANKSY feature construction")
    sc.pp.scale(adata_work, max_value=10)

    coord_keys = ("x", "y", "spatial")

    banksy_dict = initialize_banksy(
        adata_work,
        coord_keys=coord_keys,
        num_neighbours=num_neighbours,
        max_m=max_m,
        plt_edge_hist=False,
        plt_nbr_weights=False,
        plt_theta=False,
    )

    _, banksy_matrix = generate_banksy_matrix(
        adata_work, banksy_dict,
        lambda_list=[lambda_param],
        max_m=max_m, verbose=False,
    )

    sc.pp.pca(banksy_matrix, n_comps=pca_dims)
    sc.pp.neighbors(banksy_matrix, use_rep="X_pca", n_neighbors=num_neighbours)
    sc.tl.leiden(banksy_matrix, resolution=resolution, key_added="banksy_cluster")

    adata.obs["spatial_domain"] = banksy_matrix.obs["banksy_cluster"].values
    adata.obsm["X_banksy_pca"] = banksy_matrix.obsm["X_pca"]

    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("BANKSY domains: %d", actual_n)

    return {
        "method": "banksy",
        "n_domains": actual_n,
        "lambda": lambda_param,
        "resolution": resolution,
        "num_neighbours": num_neighbours,
        "original_features": adata.n_vars,
        "banksy_features": banksy_matrix.n_vars,
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


# ---------------------------------------------------------------------------
# Method dispatch
# ---------------------------------------------------------------------------


def dispatch_method(method: str, adata, **kwargs) -> dict:
    """Route to the correct domain identification function.

    Parameters
    ----------
    method : str
        One of :data:`SUPPORTED_METHODS`.
    adata : AnnData
        Preprocessed spatial data.
    **kwargs
        Passed to the chosen method function.

    Returns
    -------
    dict
        Summary with keys: method, n_domains, domain_counts, ...
    """
    _DISPATCH = {
        "leiden": identify_domains_leiden,
        "louvain": identify_domains_louvain,
        "spagcn": identify_domains_spagcn,
        "stagate": identify_domains_stagate,
        "graphst": identify_domains_graphst,
        "banksy": identify_domains_banksy,
    }

    func = _DISPATCH.get(method)
    if func is None:
        raise ValueError(f"Unknown method: {method}. Choose from {SUPPORTED_METHODS}")

    # Filter kwargs to only pass what the function accepts
    import inspect
    sig = inspect.signature(func)
    valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return func(adata, **valid_kwargs)
