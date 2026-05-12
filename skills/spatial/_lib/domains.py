"""Spatial domain identification algorithms.

Provides multiple methods for tissue region/niche identification:
  - leiden:       Graph-based clustering with spatial-weighted neighbors (default)
  - louvain:      Classic graph-based clustering
  - spagcn:       Spatial Graph Convolutional Network
  - stagate:      Graph attention auto-encoder (PyTorch Geometric)
  - graphst:      Self-supervised contrastive learning (PyTorch)
  - banksy:       Explicit spatial feature augmentation
  - cellcharter:  Neighborhood-aggregated GMM clustering (CSOgroup/cellcharter)

Usage::

    from skills.spatial._lib.domains import (
        identify_domains_leiden,
        identify_domains_spagcn,
        identify_domains_cellcharter,
        refine_spatial_domains,
        SUPPORTED_METHODS,
    )

    summary = identify_domains_leiden(adata, resolution=1.0)
    summary = identify_domains_cellcharter(adata, n_domains=7)
"""

from __future__ import annotations

import logging
from collections import Counter

import numpy as np
import pandas as pd
import scanpy as sc
import scipy.sparse as sp

from .adata_utils import ensure_neighbors, ensure_pca, get_spatial_key, require_spatial_coords

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("leiden", "louvain", "spagcn", "stagate", "graphst", "banksy", "cellcharter")


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

    Leiden operates on the **pre-built neighbor graph** derived from
    log-normalized expression + PCA. When spatial coordinates are
    available, the expression-based and spatial-based neighbor graphs are
    combined with configurable weighting.
    """
    logger.info(
        "Leiden: using pre-built neighbor graph (log-normalized + PCA); "
        "spatial_weight=%.2f", spatial_weight,
    )
    ensure_pca(adata, n_comps=n_pcs)
    ensure_neighbors(adata, n_neighbors=n_neighbors, n_pcs=min(n_pcs, 30))

    spatial_key = get_spatial_key(adata)
    adjacency = adata.obsp["connectivities"]

    if spatial_key is not None and spatial_weight > 0:
        try:
            import squidpy as sq
            sq.gr.spatial_neighbors(adata, spatial_key=spatial_key, coord_type="generic")
            if "spatial_connectivities" in adata.obsp:
                expr_w = 1.0 - spatial_weight
                # Mathematical combination without permanently overwriting adata.obsp['connectivities']
                adjacency = (
                    expr_w * adata.obsp["connectivities"]
                    + spatial_weight * adata.obsp["spatial_connectivities"]
                )
                logger.info(
                    "Dynamically integrated expression (%.0f%%) + spatial (%.0f%%) graphs",
                    expr_w * 100, spatial_weight * 100,
                )
        except Exception as e:
            logger.warning("Could not build spatial graph, using expression only: %s", e)

    sc.tl.leiden(adata, resolution=resolution, flavor="igraph", key_added="spatial_domain", adjacency=adjacency)

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
    spatial_weight: float = 0.0,
) -> dict:
    """Louvain graph clustering for spatial domain identification.

    Like Leiden, Louvain operates on the neighbor graph (derived from 
    log-normalized + PCA). If `spatial_weight > 0.0`, a composite graph is built.

    Requires the ``louvain`` Python package: pip install louvain
    """
    logger.info(
        "Louvain: using pre-built neighbor graph (log-normalized + PCA); "
        "spatial_weight=%.2f", spatial_weight,
    )
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

    spatial_key = get_spatial_key(adata)
    adjacency = adata.obsp["connectivities"]

    if spatial_key is not None and spatial_weight > 0:
        try:
            import squidpy as sq
            sq.gr.spatial_neighbors(adata, spatial_key=spatial_key, coord_type="generic")
            if "spatial_connectivities" in adata.obsp:
                expr_w = 1.0 - spatial_weight
                adjacency = (
                    expr_w * adata.obsp["connectivities"]
                    + spatial_weight * adata.obsp["spatial_connectivities"]
                )
                logger.info(
                    "Dynamically integrated expression (%.0f%%) + spatial (%.0f%%) graphs",
                    expr_w * 100, spatial_weight * 100,
                )
        except Exception as e:
            logger.warning("Could not build spatial graph, using expression only: %s", e)

    sc.tl.louvain(adata, resolution=resolution, key_added="spatial_domain", adjacency=adjacency)

    n_domains = adata.obs["spatial_domain"].nunique()
    logger.info("Louvain domains: %d (resolution=%.2f)", n_domains, resolution)

    return {
        "method": "louvain",
        "n_domains": n_domains,
        "resolution": resolution,
        "spatial_weight": spatial_weight if spatial_key else 0.0,
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def identify_domains_spagcn(
    adata,
    *,
    n_domains: int = 7,
    epochs: int | None = None,
    spagcn_p: float = 0.5,
) -> dict:
    """SpaGCN — Spatial Graph Convolutional Network for domain identification.

    Follows the official SpaGCN tutorial workflow:
    prefilter genes → normalize_per_cell → log1p → calculate_adj_matrix →
    search_l → train(init='kmeans', n_clusters=n_domains) → predict → refine.

    Note: SpaGCN 1.2.x is a CPU-only library (no CUDA support).
    Using ``init='kmeans'`` avoids the ``sc.tl.louvain`` segfault that
    occurs in Python 3.11+ with deprecated louvain C extensions.
    """
    from .dependency_manager import require

    require("SpaGCN", feature="SpaGCN spatial domain detection")

    import gc
    import scipy.sparse
    import SpaGCN

    from .adata_utils import get_spatial_key

    # SpaGCN 1.2.x calls sparse_matrix.A (removed in scipy >= 1.14).
    # Patch all common sparse types before any SpaGCN call.
    for _mat_type in (
        scipy.sparse.csr_matrix,
        scipy.sparse.csc_matrix,
        scipy.sparse.coo_matrix,
    ):
        if not hasattr(_mat_type, "A"):
            _mat_type.A = property(lambda self: self.toarray())

    spatial_key = get_spatial_key(adata)
    if spatial_key is None:
        raise ValueError("SpaGCN requires spatial coordinates, but none were found in adata.obsm.")

    # Work on a copy so the original adata is not mutated by prefiltering/normalization.
    adata_work = adata.copy()

    # --- Official tutorial preprocessing pipeline ---
    # Step 1: prefilter lowly-expressed and special (MT/ERCC) genes.
    try:
        SpaGCN.prefilter_genes(adata_work, min_cells=3)
        SpaGCN.prefilter_specialgenes(adata_work)
        logger.info("SpaGCN: prefiltered to %d genes", adata_work.n_vars)
    except Exception as e:
        logger.warning("SpaGCN gene prefiltering skipped: %s", e)

    # Step 2: normalize and log-transform only if data looks like raw counts.
    X = adata_work.X
    X_sample = X[:min(100, X.shape[0])].toarray() if scipy.sparse.issparse(X) else X[:min(100, X.shape[0])]
    if np.allclose(X_sample, X_sample.astype(int)):
        logger.info("SpaGCN: data looks like raw counts, applying normalize_per_cell + log1p")
        sc.pp.normalize_per_cell(adata_work)
        sc.pp.log1p(adata_work)

    logger.info(
        "SpaGCN: using log-normalized expression (%d genes) + spatial coordinates",
        adata_work.n_vars,
    )

    coords = adata_work.obsm[spatial_key]
    x_coord = coords[:, 0].astype(float)
    y_coord = coords[:, 1].astype(float)

    # Step 3: build adjacency matrix and tune spatial kernel scale.
    logger.info("Building SpaGCN adjacency matrix ...")
    adj = SpaGCN.calculate_adj_matrix(x=x_coord, y=y_coord, histology=False)
    l_value = SpaGCN.search_l(spagcn_p, adj, start=0.01, end=1000, tol=0.01, max_run=100)
    logger.info("SpaGCN optimized l-parameter: %.4f (for p=%.2f)", l_value, spagcn_p)

    # Auto-detect tissue geometry for boundary refinement.
    shape = "square"
    if "spatial" in adata.uns:
        for k, v in adata.uns["spatial"].items():
            if "visium" in str(k).lower() or "visium" in str(v).lower():
                shape = "hexagon"
                break
    logger.info("SpaGCN refine topology shape mode: %s", shape)

    # Step 4: train.
    # Use init='kmeans' with n_clusters=n_domains to avoid the sc.tl.louvain
    # segfault caused by deprecated louvain C extensions in Python 3.11+.
    clf = SpaGCN.SpaGCN()
    clf.set_l(l_value)
    clf.train(
        adata_work, adj,
        num_pcs=50,
        init_spa=True,
        init="kmeans",
        n_clusters=n_domains,
        tol=5e-3,
        lr=0.05,
        max_epochs=epochs if epochs is not None else 200,
    )

    # Step 5: predict and refine.
    y_pred, _ = clf.predict()
    adata.obs["spatial_domain"] = pd.Categorical(y_pred.astype(str))

    logger.info("Running spatial domain boundary refinement...")
    try:
        refined = SpaGCN.refine(
            sample_id=adata.obs.index.tolist(),
            pred=y_pred, dis=adj, shape=shape,
        )
        adata.obs["spatial_domain"] = pd.Categorical([str(r) for r in refined])
    except Exception as e:
        logger.warning(
            "SpaGCN refinement failed (shape=%s), using unrefined predictions: %s",
            shape, e,
        )

    del clf, adata_work
    gc.collect()

    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("SpaGCN domains: %d (requested %d)", actual_n, n_domains)

    return {
        "method": "spagcn",
        "n_domains": actual_n,
        "n_domains_requested": n_domains,
        "topology_shape": shape,
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def identify_domains_stagate(
    adata,
    *,
    n_domains: int = 7,
    rad_cutoff: float | None = None,
    k_nn: int | None = 6,
    stagate_alpha: float = 0.0,
    pre_resolution: float = 0.2,
    epochs: int | None = None,
    random_seed: int = 42,
) -> dict:
    """STAGATE — graph attention auto-encoder for spatial domain identification.

    Uses **log-normalized expression** (``adata.X``), automatically subsetted
    to highly variable genes when available.
    Spatial network is built preferably via scale-invariant KNN (`k_nn=6`)
    rather than a fixed radius to support diverse spatial resolutions.
    """
    from .dependency_manager import require

    require("STAGATE_pyG", feature="STAGATE spatial domain identification")
    require("torch", feature="STAGATE (PyTorch backend)")

    import torch
    import STAGATE_pyG
    import gc

    logger.info("Running STAGATE (k_nn=%s, rad_cutoff=%s, n_domains=%d) ...", k_nn, rad_cutoff, n_domains)

    if "highly_variable" in adata.var.columns and adata.var["highly_variable"].sum() > 0:
        n_hvg = adata.var["highly_variable"].sum()
        logger.info("Subsetting to %d HVGs for STAGATE autoencoder", n_hvg)
        adata_work = adata[:, adata.var["highly_variable"]].copy()
    else:
        logger.warning(
            "No valid 'highly_variable' mask found; using all %d genes. "
            "Consider running sc.pp.highly_variable_genes() first to prevent VRAM explosion.",
            adata.n_vars,
        )
        adata_work = adata.copy()

    # Build Spatial Network
    # KNN is strongly preferred as it is invariant to coordinate scaling (Stereo-seq vs Visium)
    if k_nn is not None and k_nn > 0:
        logger.info("Building STAGATE network using adaptive KNN (k=%d)", k_nn)
        STAGATE_pyG.Cal_Spatial_Net(adata_work, model='KNN', k_cutoff=k_nn)
    elif rad_cutoff is not None and rad_cutoff > 0:
        logger.warning("Building STAGATE network using static radius (rad=%.1f). May fail if coordinate scales misalign.", rad_cutoff)
        STAGATE_pyG.Cal_Spatial_Net(adata_work, model='Radius', rad_cutoff=rad_cutoff)
    else:
        logger.warning("No spatial geometry passed. Falling back to scale-invariant KNN (k=6).")
        STAGATE_pyG.Cal_Spatial_Net(adata_work, model='KNN', k_cutoff=6)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("STAGATE device: %s", device)
    
    if device.type == "cuda":
        torch.cuda.empty_cache()

    train_kwargs = {}
    if stagate_alpha > 0:
        train_kwargs["alpha"] = stagate_alpha
        train_kwargs["pre_resolution"] = pre_resolution
    if epochs is not None:
        train_kwargs["n_epochs"] = epochs

    try:
        adata_work = STAGATE_pyG.train_STAGATE(adata_work, device=device, **train_kwargs)
    finally:
        # Mandatory cleanup to prevent CUDA OOM across multiple runs
        if device.type == "cuda":
            torch.cuda.empty_cache()
        gc.collect()

    from sklearn.mixture import GaussianMixture
    from sklearn.cluster import KMeans

    embedding = adata_work.obsm["STAGATE"]
    try:
        gmm = GaussianMixture(
            n_components=n_domains, covariance_type="tied",
            random_state=random_seed, reg_covar=1e-3,  # Increased reg_covar for conditioning
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
        "k_nn": k_nn,
        "rad_cutoff": rad_cutoff,
        "clustering": clustering_name,
        "device": str(device),
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def identify_domains_graphst(
    adata,
    *,
    n_domains: int = 7,
    epochs: int | None = None,
    dim_output: int = 64,
    random_seed: int = 42,
    datatype: str | None = None,
    refine: bool = False,
    refine_radius: int = 50,
) -> dict:
    """GraphST — self-supervised contrastive learning for spatial domains.

    Follows the official GraphST tutorial (JinmiaoChenLab/GraphST):
    - Restores raw counts to avoid double log-transform
    - Detects data platform (Stereo-seq, Visium, 10X, etc.) for optimised graph construction
    - Trains the GNN model
    - Clusters via official ``GraphST.utils.clustering()``:
        mclust (recommended) → leiden → louvain
    - Optionally applies ``refine_label`` post-processing

    Parameters
    ----------
    datatype : str or None
        Platform hint: 'Stereo', 'Visium', '10X' etc.
        Auto-detected from adata.uns if None.
    refine : bool
        Apply KNN spatial label refinement (official GraphST post-processing).
    refine_radius : int
        Neighbourhood size for refinement (default 50).
    """
    from .dependency_manager import require

    require("GraphST", feature="GraphST spatial domain identification")
    require("torch", feature="GraphST (PyTorch backend)")

    import torch
    import gc

    def _resolve_graphst_datatype(
        graph_adata,
        explicit_datatype: str | None,
    ) -> str:
        if explicit_datatype:
            token = str(explicit_datatype).strip().lower()
        else:
            token_parts = [
                str(graph_adata.uns.get("platform", "") or ""),
                str(graph_adata.uns.get("data_type", "") or ""),
                str(graph_adata.uns.get("spatial_name", "") or ""),
                str(graph_adata.uns.get("dataset_name", "") or ""),
            ]
            token = " ".join(token_parts).strip().lower()

        if any(key in token for key in ("slide", "slide_seq", "slideseq")):
            return "Slide"
        if any(key in token for key in ("stereo", "stereoseq", "stereo-seq")):
            return "Stereo"
        if any(key in token for key in ("visium", "10x", "10 x")):
            return "10X"
        return "10X"

    def _is_graphst_sparse_datatype(value: str) -> bool:
        return str(value).strip().lower() in {"slide", "stereo"}

    logger.info("Running GraphST (n_domains=%s, epochs=%s, dim_output=%d) ...",
                n_domains, epochs, dim_output)

    # ------------------------------------------------------------------
    # 1. Restore raw counts (GraphST.preprocess does its own normalisation)
    # ------------------------------------------------------------------
    if "counts" in adata.layers:
        logger.info("Restoring raw counts from adata.layers['counts']")
        adata_work = adata.copy()
        adata_work.X = adata_work.layers["counts"].copy()
    elif adata.raw is not None:
        logger.info("Restoring raw counts from adata.raw")
        adata_work = adata.raw.to_adata().copy()
        spatial_key = get_spatial_key(adata)
        if spatial_key and spatial_key in adata.obsm:
            adata_work.obsm[spatial_key] = adata.obsm[spatial_key]
    else:
        logger.warning(
            "No raw counts found (layers['counts'] / adata.raw). "
            "Using adata.X — results may be suboptimal if already log-normalised."
        )
        adata_work = adata.copy()

    # GraphST strictly expects geometry in 'spatial'
    spatial_key = get_spatial_key(adata_work)
    if spatial_key and spatial_key != "spatial":
        adata_work.obsm["spatial"] = adata_work.obsm[spatial_key]

    detected_datatype = _resolve_graphst_datatype(adata_work, datatype)
    logger.info("GraphST datatype resolved to %s", detected_datatype)

    if _is_graphst_sparse_datatype(detected_datatype):
        _prepare_graphst_sparse_slide_graph(adata_work)

    # ------------------------------------------------------------------
    # 2. GPU setup
    # ------------------------------------------------------------------
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cuda":
        torch.cuda.empty_cache()
        logger.info("GraphST using CUDA accelerator")
    else:
        logger.info("GraphST using CPU")

    # ------------------------------------------------------------------
    # 3. Build model + train  (official tutorial: GraphST(adata, datatype=..., device=...))
    # ------------------------------------------------------------------
    from GraphST.GraphST import GraphST as GraphSTModel

    _patch_graphst_sparse_init()
    _patch_graphst_sparse_readout()

    model = None
    try:
        model_kwargs: dict = {
            "device": device,
            "random_seed": random_seed,
            "datatype": detected_datatype,
        }
        if dim_output != 64:
            model_kwargs["dim_output"] = dim_output
        if epochs is not None:
            model_kwargs["epochs"] = epochs

        model = GraphSTModel(adata_work, **model_kwargs)

        # Some versions ignore the constructor `epochs`; patch directly
        if epochs is not None and hasattr(model, "epochs") and model.epochs != epochs:
            model.epochs = epochs

        adata_work = model.train()
    finally:
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()
        gc.collect()

    # ------------------------------------------------------------------
    # 4. Clustering
    # ------------------------------------------------------------------
    labels, clustering_name = _cluster_graphst_embedding(
        adata_work,
        n_domains,
        random_seed=random_seed,
    )
    logger.info("GraphST clustering: %s", clustering_name)

    # ------------------------------------------------------------------
    # 6. Optional label refinement (official GraphST.utils.refine_label)
    # ------------------------------------------------------------------
    if refine:
        try:
            from GraphST.utils import refine_label
            new_labels = refine_label(adata_work, radius=refine_radius, key="domain")
            labels = np.array(new_labels)
            logger.info("GraphST refine_label applied (radius=%d)", refine_radius)
        except Exception as e:
            logger.warning("refine_label failed (%s), using unrefined labels", e)

    adata.obs["spatial_domain"] = pd.Categorical(np.array(labels).astype(str))
    adata.obsm["X_graphst"] = adata_work.obsm["emb"]

    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("GraphST domains: %d (requested %d)", actual_n, n_domains)

    return {
        "method": "graphst",
        "n_domains": actual_n,
        "n_domains_requested": n_domains,
        "clustering": clustering_name,
        "datatype": detected_datatype,
        "device": str(device),
        "refined": refine,
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def _cluster_graphst_embedding(
    adata,
    n_domains: int,
    *,
    random_seed: int = 42,
    large_threshold: int = 30000,
):
    """Cluster GraphST embeddings without slow resolution scans on large data."""
    from sklearn.decomposition import PCA

    embedding = np.asarray(adata.obsm["emb"])
    n_pca = min(20, embedding.shape[1], embedding.shape[0] - 1)
    emb_pca = PCA(n_pca, random_state=random_seed).fit_transform(embedding)
    adata.obsm["emb_pca"] = emb_pca

    if adata.n_obs >= large_threshold:
        from sklearn.cluster import MiniBatchKMeans

        labels = MiniBatchKMeans(
            n_clusters=n_domains,
            random_state=random_seed,
            n_init=10,
            batch_size=min(4096, adata.n_obs),
        ).fit_predict(emb_pca)
        return labels, "minibatch_kmeans"

    from GraphST.utils import clustering as graphst_clustering

    for tool in ("mclust", "leiden", "louvain"):
        try:
            if tool == "mclust":
                graphst_clustering(adata, n_domains, method="mclust")
            else:
                graphst_clustering(
                    adata,
                    n_domains,
                    method=tool,
                    start=0.1,
                    end=2.0,
                    increment=0.01,
                )
            if "domain" in adata.obs:
                return adata.obs["domain"].values, tool
        except Exception as e:
            logger.info("GraphST clustering '%s' failed (%s), trying next", tool, e)

    from sklearn.cluster import KMeans

    logger.warning("All GraphST clustering methods failed, using KMeans on emb_pca")
    labels = KMeans(
        n_clusters=n_domains,
        random_state=random_seed,
        n_init=10,
    ).fit_predict(emb_pca)
    return labels, "kmeans"


def _prepare_graphst_sparse_slide_graph(adata, *, n_neighbors: int = 3) -> None:
    """Prebuild GraphST's Slide/Stereo interaction graph as scipy sparse matrices.

    Upstream GraphST's ``construct_interaction_KNN`` stores both
    ``obsm['adj']`` and ``obsm['graph_neigh']`` as dense ``n_obs x n_obs``
    numpy arrays. For high-resolution Slide-seq datasets this can require
    tens of GB before a single epoch starts. GraphST accepts scipy sparse
    adjacency for its sparse encoder, and PyTorch can multiply a sparse
    readout mask with dense embeddings, so keep both graph objects sparse.
    """
    from sklearn.neighbors import NearestNeighbors

    spatial_key = get_spatial_key(adata)
    if spatial_key is None:
        raise ValueError("GraphST requires spatial coordinates in adata.obsm.")

    coords = np.asarray(adata.obsm[spatial_key])[:, :2]
    n_spot = coords.shape[0]
    k = max(1, min(int(n_neighbors), n_spot - 1))
    nbrs = NearestNeighbors(n_neighbors=k + 1).fit(coords)
    _, indices = nbrs.kneighbors(coords)

    rows = np.repeat(np.arange(n_spot), k)
    cols = indices[:, 1 : k + 1].reshape(-1)
    data = np.ones(rows.shape[0], dtype=np.float32)
    interaction = sp.csr_matrix((data, (rows, cols)), shape=(n_spot, n_spot))
    adjacency = (interaction + interaction.T).sign().astype(np.float32).tocsr()

    adata.obsm["graph_neigh"] = interaction
    adata.obsm["adj"] = adjacency
    logger.info(
        "GraphST prebuilt sparse spatial graph: n_obs=%d, k=%d, nnz=%d",
        n_spot,
        k,
        int(adjacency.nnz),
    )


def _scipy_to_torch_sparse_tensor(sparse_mx, *, device=None):
    """Convert a scipy sparse matrix to a coalesced torch sparse COO tensor."""
    import torch

    sparse_mx = sparse_mx.tocoo().astype(np.float32)
    indices = torch.from_numpy(np.vstack((sparse_mx.row, sparse_mx.col)).astype(np.int64))
    values = torch.from_numpy(sparse_mx.data.astype(np.float32, copy=False))
    tensor = torch.sparse_coo_tensor(
        indices,
        values,
        torch.Size(sparse_mx.shape),
        dtype=torch.float32,
    ).coalesce()
    if device is not None:
        tensor = tensor.to(device)
    return tensor


def _patch_graphst_sparse_init() -> None:
    """Prevent upstream GraphST from densifying prebuilt Slide/Stereo graphs."""
    try:
        import inspect
        import importlib
        import torch

        graphst_module = importlib.import_module("GraphST.GraphST")
    except Exception:
        return

    graphst_cls = getattr(graphst_module, "GraphST", None)
    if graphst_cls is None or getattr(graphst_cls, "_omicsclaw_sparse_init_patch", False):
        return

    original_init = graphst_cls.__init__
    signature = inspect.signature(original_init)

    def __init__(self, adata, *args, **kwargs):
        bound = signature.bind(self, adata, *args, **kwargs)
        bound.apply_defaults()
        params = bound.arguments

        datatype = params["datatype"]
        deconvolution = params["deconvolution"]
        has_sparse_graph = (
            datatype in {"Stereo", "Slide"}
            and not deconvolution
            and "adj" in adata.obsm
            and "graph_neigh" in adata.obsm
            and sp.issparse(adata.obsm["adj"])
            and sp.issparse(adata.obsm["graph_neigh"])
        )
        if not has_sparse_graph:
            return original_init(self, adata, *args, **kwargs)

        self.adata = adata.copy()
        self.device = params["device"]
        self.learning_rate = params["learning_rate"]
        self.learning_rate_sc = params["learning_rate_sc"]
        self.weight_decay = params["weight_decay"]
        self.epochs = params["epochs"]
        self.random_seed = params["random_seed"]
        self.alpha = params["alpha"]
        self.beta = params["beta"]
        self.theta = params["theta"]
        self.lamda1 = params["lamda1"]
        self.lamda2 = params["lamda2"]
        self.deconvolution = deconvolution
        self.datatype = datatype

        graphst_module.fix_seed(self.random_seed)

        if "highly_variable" not in adata.var.keys():
            graphst_module.preprocess(self.adata)
        if "label_CSL" not in adata.obsm.keys():
            graphst_module.add_contrastive_label(self.adata)
        if "feat" not in adata.obsm.keys():
            graphst_module.get_feature(self.adata)

        self.features = torch.FloatTensor(self.adata.obsm["feat"].copy()).to(self.device)
        self.features_a = torch.FloatTensor(self.adata.obsm["feat_a"].copy()).to(self.device)
        self.label_CSL = torch.FloatTensor(self.adata.obsm["label_CSL"]).to(self.device)

        self.adj = self.adata.obsm["adj"]
        graph_neigh = self.adata.obsm["graph_neigh"].copy()
        graph_neigh = (graph_neigh + sp.eye(graph_neigh.shape[0], format="csr")).tocsr()
        self.graph_neigh = _scipy_to_torch_sparse_tensor(graph_neigh, device=self.device)

        self.dim_input = self.features.shape[1]
        self.dim_output = params["dim_output"]
        self.adj = graphst_module.preprocess_adj_sparse(self.adj).to(self.device)

    graphst_cls.__init__ = __init__
    graphst_cls._omicsclaw_sparse_init_patch = True
    graphst_cls._omicsclaw_original_init = original_init


def _patch_graphst_sparse_readout() -> None:
    """Allow upstream GraphST AvgReadout to consume sparse graph_neigh masks."""
    try:
        from GraphST import model as graphst_model
        import torch
        import torch.nn.functional as F
    except Exception:
        return

    readout_cls = getattr(graphst_model, "AvgReadout", None)
    if readout_cls is None or getattr(readout_cls, "_omicsclaw_sparse_patch", False):
        return

    def forward(self, emb, mask=None):
        if mask is not None and getattr(mask, "is_sparse", False):
            vsum = torch.mm(mask, emb)
            row_sum = torch.sparse.sum(mask, dim=1).to_dense().clamp_min(1.0)
            row_sum = row_sum.unsqueeze(1).expand(-1, vsum.shape[1])
            return F.normalize(vsum / row_sum, p=2, dim=1)
        vsum = torch.mm(mask, emb)
        row_sum = torch.sum(mask, 1)
        row_sum = row_sum.expand((vsum.shape[1], row_sum.shape[0])).T
        global_emb = vsum / row_sum
        return F.normalize(global_emb, p=2, dim=1)

    readout_cls.forward = forward
    readout_cls._omicsclaw_sparse_patch = True


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

    BANKSY requires numpy<2.0 which conflicts with the main env's numpy>=2.0
    (transitively via scvi-tools/numba). Therefore this runs in a dedicated
    sub-env `omicsclaw_banksy` via subprocess; the BANKSY algorithm itself
    lives in skills/spatial/_lib/_runners/banksy_runner.py.

    Bootstrap the sub-env once via: `bash 0_setup_env.sh --with-banksy`
    (or `OMICSCLAW_WITH_BANKSY=1 bash 0_setup_env.sh`).

    Mutates `adata` in place (sets adata.obs['spatial_domain'] and
    adata.obsm['X_banksy_pca']). Returns a metadata dict.
    """
    from pathlib import Path
    from omicsclaw.core.external_env import (
        EnvNotFoundError,
        is_env_available,
        run_anndata_op_in_env,
    )

    sub_env = "omicsclaw_banksy"
    if not is_env_available(sub_env):
        raise EnvNotFoundError(
            f"BANKSY requires the {sub_env!r} sub-env (numpy<2.0). "
            "Create it via: bash 0_setup_env.sh --with-banksy"
        )

    runner = (
        Path(__file__).resolve().parent / "_runners" / "banksy_runner.py"
    )
    params = {
        "n_domains": n_domains,
        "resolution": resolution,
        "lambda_param": lambda_param,
        "num_neighbours": num_neighbours,
        "max_m": max_m,
        "pca_dims": pca_dims,
    }

    logger.info(
        "BANKSY: dispatching to sub-env %s (lambda=%.2f, n_domains=%s, "
        "resolution=%.2f)", sub_env, lambda_param, n_domains, resolution,
    )

    adata_out = run_anndata_op_in_env(
        env=sub_env,
        runner_script=runner,
        adata=adata,
        params=params,
    )

    # Propagate sub-env results back into the caller's AnnData.
    adata.obs["spatial_domain"] = adata_out.obs["spatial_domain"].values
    adata.obsm["X_banksy_pca"] = adata_out.obsm["X_banksy_pca"]

    return dict(adata_out.uns.get("banksy_meta", {}))



def identify_domains_cellcharter(
    adata,
    *,
    n_domains: int | None = 7,
    n_layers: int = 3,
    use_rep: str | None = None,
    delaunay: bool = True,
    remove_long_links: bool = True,
    auto_k: bool = False,
    auto_k_min: int = 2,
    auto_k_max: int | None = None,
    max_runs: int = 5,
    convergence_tol: float = 0.01,
    random_seed: int = 42,
    sample_key: str | None = None,
    accelerator: str = "auto",
) -> dict:
    """CellCharter — neighborhood-aggregated GMM for spatial domain identification.

    Implements the official CellCharter tutorial workflow:

    1. **Spatial graph**: ``sq.gr.spatial_neighbors(..., delaunay=True)`` to
       build a cell-proximity network.
    2. **Remove long links** (optional): ``cc.gr.remove_long_links()`` removes
       spurious long-range Delaunay edges (>99th-percentile length).
    3. **Neighbor aggregation**: ``cc.gr.aggregate_neighbors(n_layers=n_layers)``
       concatenates the cell's own features with mean-aggregated features from
       each hop of spatial neighbors → stored in ``adata.obsm["X_cellcharter"]``.
    4. **Clustering**:
       - Fixed K: ``cc.tl.Cluster(n_clusters=n_domains)`` — single GMM fit.
       - Auto K: Stability-based selection — repeats clustering for each K
         and picks the most stable one (workaround for CellCharter 0.3.7 bug).

    Parameters
    ----------
    n_domains :
        Number of spatial domains (clusters). Ignored when ``auto_k=True``.
    n_layers :
        Number of neighborhood hops to aggregate (default 3).
        The final feature vector length is ``n_features × (n_layers + 1)``.
    use_rep :
        ``obsm`` key of the input feature matrix (e.g. ``"X_pca"``,
        ``"X_scVI"``). If *None*, ``adata.X`` is used.
    delaunay :
        If *True* (default), use Delaunay triangulation when building the
        spatial graph. Otherwise fallen back to a K-NN / radius approach.
    remove_long_links :
        Apply ``cc.gr.remove_long_links()`` to prune spurious long-range edges
        created by Delaunay triangulation (strongly recommended).
    auto_k :
        Enable automatic selection of the best number of clusters via
        stability analysis.
    auto_k_min :
        Minimum K to evaluate when ``auto_k=True`` (default 2).
    auto_k_max :
        Maximum K to evaluate when ``auto_k=True``. Defaults to
        ``n_domains`` if provided, else ``auto_k_min + 8``.
    max_runs :
        Maximum repetitions per K for stability analysis (default 5).
    convergence_tol :
        Stop early when mean stability improvement drops below this threshold
        (default 0.01). Currently unused but reserved for future optimization.
    random_seed :
        Reproducibility seed (default 42).
    sample_key :
        Column in ``adata.obs`` identifying sample membership. Required when
        ``adata`` contains multiple samples.
    accelerator :
        PyTorch Lightning accelerator: ``"cpu"``, ``"gpu"``, or ``"auto"``
        (default). ``"auto"`` uses GPU when available.

    Returns
    -------
    dict
        ``method``, ``n_domains``, ``n_domains_requested``, ``n_layers``,
        ``use_rep``, ``clustering``, ``device``, ``domain_counts``.
    """
    from .dependency_manager import require
    import gc
    import inspect
    from sklearn.metrics import adjusted_rand_score
    from collections import defaultdict

    cc = require("cellcharter", feature="CellCharter spatial domain identification")
    sq = require("squidpy", feature="CellCharter (spatial graph construction)")

    logger.info(
        "Running CellCharter (n_domains=%s, n_layers=%d, use_rep=%s, auto_k=%s) ...",
        n_domains, n_layers, use_rep, auto_k,
    )

    # ------------------------------------------------------------------
    # 1. Determine feature representation
    # ------------------------------------------------------------------
    if use_rep is None:
        if "X_pca" not in adata.obsm:
            logger.warning(
                "CellCharter requires a low-dimensional embedding (like PCA) to run efficiently\n"
                "and avoid covariance matrix singularities in GMM with raw genes.\n"
                "Computing PCA now (n_comps=min(50, n_vars-1))..."
            )
            ensure_pca(adata, n_comps=min(30, adata.n_vars - 1))
        
        use_rep = "X_pca"
        logger.info("CellCharter: using use_rep='%s'", use_rep)

    # ------------------------------------------------------------------
    # 2. Build spatial neighbors graph
    # ------------------------------------------------------------------
    spatial_key = get_spatial_key(adata)
    if spatial_key is None:
        raise ValueError(
            "CellCharter requires spatial coordinates in adata.obsm, "
            "but none were found. Ensure 'spatial' or 'X_spatial' is present."
        )

    logger.info("Building spatial neighbors graph (delaunay=%s) ...", delaunay)
    sq_kwargs: dict = {
        "coord_type": "generic",
        "spatial_key": spatial_key,
        "delaunay": delaunay,
    }
    if sample_key is not None:
        sq_kwargs["library_key"] = sample_key

    sq.gr.spatial_neighbors(adata, **sq_kwargs)

    # ------------------------------------------------------------------
    # 3. Remove spurious long-range Delaunay links (highly recommended)
    # ------------------------------------------------------------------
    if remove_long_links and delaunay:
        try:
            cc.gr.remove_long_links(adata)
            logger.info("CellCharter: long links removed (>99th-percentile edge length)")
        except Exception as e:
            logger.warning("cc.gr.remove_long_links failed (%s), skipping", e)

    # ------------------------------------------------------------------
    # 4. Aggregate neighborhood features
    # ------------------------------------------------------------------
    agg_kwargs: dict = {
        "n_layers": n_layers,
        "out_key": "X_cellcharter",
    }
    if use_rep is not None:
        agg_kwargs["use_rep"] = use_rep
    if sample_key is not None:
        agg_kwargs["sample_key"] = sample_key

    logger.info(
        "Aggregating %d-hop neighborhood features (use_rep=%s) ...", n_layers, use_rep
    )
    res = cc.gr.aggregate_neighbors(adata, **agg_kwargs)
    
    # Handle the variable behavior of out_key and copy defaults across versions
    if res is not None:
        if hasattr(res, "obsm") and "X_cellcharter" in res.obsm:
            adata.obsm["X_cellcharter"] = res.obsm["X_cellcharter"].copy()
        elif hasattr(res, "shape"): # numpy or dask array
            adata.obsm["X_cellcharter"] = res
            
    if "X_cellcharter" not in adata.obsm:
        raise ValueError("CellCharter failed to write 'X_cellcharter' into adata.obsm.")

    # ------------------------------------------------------------------
    # 5. Resolve accelerator and trainer parameters
    # ------------------------------------------------------------------
    if accelerator == "auto":
        try:
            import torch
            resolved_accelerator = "gpu" if torch.cuda.is_available() else "cpu"
        except ImportError:
            resolved_accelerator = "cpu"
    else:
        resolved_accelerator = accelerator
    logger.info("CellCharter accelerator: %s", resolved_accelerator)

    trainer_params: dict = {
        "accelerator": resolved_accelerator,
        "enable_progress_bar": False,
    }
    if resolved_accelerator == "gpu":
        trainer_params["devices"] = 1

    # Determine correct parameter name for trainer config
    ClusterClass = getattr(cc.tl, "Cluster", getattr(cc.tl, "GaussianMixture", None))
    if ClusterClass is None:
        raise AttributeError("Cannot find 'Cluster' or 'GaussianMixture' in cellcharter.tl")

    sig = inspect.signature(ClusterClass)
    trainer_arg = "trainer_params" if "trainer_params" in sig.parameters else "trainer_kwargs"

    # ------------------------------------------------------------------
    # 6. Clustering
    # ------------------------------------------------------------------
    try:
        if auto_k:
            best_k, labels, clustering_name = _cluster_auto_k(
                adata=adata,
                ClusterClass=ClusterClass,
                trainer_arg=trainer_arg,
                trainer_params=trainer_params,
                auto_k_min=auto_k_min,
                auto_k_max=auto_k_max if auto_k_max is not None else (
                    n_domains if n_domains is not None else auto_k_min + 8
                ),
                max_runs=max_runs,
                random_seed=random_seed,
            )
        else:
            best_k, labels, clustering_name = _cluster_fixed_k(
                adata=adata,
                ClusterClass=ClusterClass,
                trainer_arg=trainer_arg,
                trainer_params=trainer_params,
                n_domains=n_domains,
                random_seed=random_seed,
            )
    finally:
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # 7. Store results
    # ------------------------------------------------------------------
    adata.obs["spatial_domain"] = pd.Categorical(np.array(labels).astype(str))
    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("CellCharter domains: %d (requested %s)", actual_n, n_domains)

    return {
        "method": "cellcharter",
        "n_domains": actual_n,
        "n_domains_requested": best_k,
        "n_layers": n_layers,
        "use_rep": use_rep if use_rep is not None else "X",
        "clustering": clustering_name,
        "device": resolved_accelerator,
        "auto_k": auto_k,
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def _cluster_fixed_k(
    adata,
    ClusterClass,
    trainer_arg: str,
    trainer_params: dict,
    n_domains: int | None,
    random_seed: int,
) -> tuple[int, pd.Categorical, str]:
    """Fixed-K clustering using CellCharter Cluster/GaussianMixture.

    Returns
    -------
    tuple
        (best_k, labels, clustering_name)
    """
    if n_domains is None or n_domains < 1:
        raise ValueError(
            "n_domains must be a positive integer when auto_k=False. "
            "Set --n-domains or enable --cellcharter-auto-k."
        )

    gmm_kwargs = {
        "n_clusters": n_domains,
        "random_state": random_seed,
        trainer_arg: trainer_params,
    }
    gmm = ClusterClass(**gmm_kwargs)
    gmm.fit(adata, use_rep="X_cellcharter")
    labels = gmm.predict(adata, use_rep="X_cellcharter")

    return n_domains, labels, "gmm"


def _cluster_auto_k(
    adata,
    ClusterClass,
    trainer_arg: str,
    trainer_params: dict,
    auto_k_min: int,
    auto_k_max: int,
    max_runs: int,
    random_seed: int,
) -> tuple[int, pd.Categorical, str]:
    """Automatic K selection via stability analysis.

    Workaround for CellCharter 0.3.7 bug where ClusterAutoK passes numpy
    arrays to Cluster.fit() which expects AnnData objects.

    Implements stability-based K selection:
    1. For each K in range, run multiple clustering iterations
    2. Compute Adjusted Rand Index (ARI) between consecutive runs
    3. Select K with highest mean stability

    Returns
    -------
    tuple
        (best_k, labels, clustering_name)
    """
    from sklearn.metrics import adjusted_rand_score
    from collections import defaultdict

    logger.info(
        "CellCharter auto-K: evaluating K in [%d, %d] (max_runs=%d) ...",
        auto_k_min, auto_k_max, max_runs,
    )

    k_range = list(range(auto_k_min, auto_k_max + 1))
    stability_scores = defaultdict(list)
    best_models = {}
    prev_labels = None

    # Run multiple iterations for each K
    for run_idx in range(max_runs):
        logger.info("  Iteration %d/%d", run_idx + 1, max_runs)
        run_labels = {}

        for k in k_range:
            gmm_kwargs = {
                "n_clusters": k,
                "random_state": random_seed + run_idx,
                trainer_arg: trainer_params,
            }
            gmm = ClusterClass(**gmm_kwargs)
            gmm.fit(adata, use_rep="X_cellcharter")
            labels_k = gmm.predict(adata, use_rep="X_cellcharter")
            run_labels[k] = labels_k

            # Track best model by negative log-likelihood
            if k not in best_models or gmm.nll_ < best_models[k].nll_:
                best_models[k] = gmm

        # Compute stability (ARI between consecutive runs)
        if run_idx > 0:
            for k in k_range:
                ari = adjusted_rand_score(prev_labels[k], run_labels[k])
                stability_scores[k].append(ari)

        prev_labels = run_labels

    # Select K with highest mean stability
    if stability_scores:
        mean_stability = {k: np.mean(scores) for k, scores in stability_scores.items()}
        best_k = max(mean_stability, key=mean_stability.get)
        logger.info(
            "CellCharter auto-K selected K=%d (stability=%.3f)",
            best_k, mean_stability[best_k]
        )
    else:
        # Fallback if only one run
        best_k = (auto_k_min + auto_k_max) // 2
        logger.warning("Only one run, using K=%d (midpoint)", best_k)

    # Use the best model for final prediction
    labels = best_models[best_k].predict(adata, use_rep="X_cellcharter")
    clustering_name = f"autok_gmm(best_k={best_k})"

    return best_k, labels, clustering_name


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
        "cellcharter": identify_domains_cellcharter,
    }

    func = _DISPATCH.get(method)
    if func is None:
        raise ValueError(f"Unknown method: {method}. Choose from {SUPPORTED_METHODS}")

    # Filter kwargs to only pass what the function accepts
    import inspect
    sig = inspect.signature(func)
    valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}

    if method == "graphst" and "datatype" in sig.parameters and "datatype" not in valid_kwargs:
        data_type = kwargs.get("data_type")
        if data_type is not None:
            valid_kwargs["datatype"] = data_type
    return func(adata, **valid_kwargs)
