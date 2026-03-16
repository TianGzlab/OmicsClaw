#!/usr/bin/env python3
"""Spatial Domains — identify tissue regions and spatial niches.

Supports multiple algorithms with distinct strengths:
  - leiden:   Graph-based clustering with spatial-weighted neighbors (default, fast)
  - louvain:  Classic graph-based clustering (requires: pip install louvain)
  - spagcn:   Spatial Graph Convolutional Network (integrates histology)
  - stagate:  Graph attention auto-encoder (PyTorch Geometric)
  - graphst:  Self-supervised contrastive learning (PyTorch)
  - banksy:   Explicit spatial feature augmentation (interpretable)

Usage:
    python spatial_domains.py --input <preprocessed.h5ad> --output <dir>
    python spatial_domains.py --demo --output <dir>
    python spatial_domains.py --input <file> --method spagcn --n-domains 7 --output <dir>
    python spatial_domains.py --input <file> --method stagate --n-domains 7 --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.spatial.adata_utils import (
    ensure_neighbors,
    ensure_pca,
    get_spatial_key,
    require_spatial_coords,
    store_analysis_metadata,
)
from omicsclaw.spatial.viz_utils import save_figure
from omicsclaw.spatial.viz import VizParams, plot_features, plot_integration

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-domains"
SKILL_VERSION = "0.3.0"

SUPPORTED_METHODS = ("leiden", "louvain", "spagcn", "stagate", "graphst", "banksy")


# ---------------------------------------------------------------------------
# Spatial domain refinement (shared across methods, following SpaGCN paper)
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

    Requires the ``louvain`` Python package:
        pip install louvain
    """
    ensure_pca(adata, n_comps=n_pcs)
    ensure_neighbors(adata, n_neighbors=n_neighbors, n_pcs=min(n_pcs, 30))

    try:
        import louvain as _  # noqa: F401 — check availability before calling sc.tl.louvain
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
    from omicsclaw.spatial.dependency_manager import require

    require("SpaGCN", feature="SpaGCN spatial domain detection")

    import scipy.sparse
    import SpaGCN

    # SpaGCN 1.2.7 uses .A (removed in scipy >= 1.14); patch csr_matrix for compatibility
    if not hasattr(scipy.sparse.csr_matrix, "A"):
        scipy.sparse.csr_matrix.A = property(lambda self: self.toarray())

    spatial_key = require_spatial_coords(adata)
    coords = adata.obsm[spatial_key]

    x_pixel = coords[:, 0].astype(float)
    y_pixel = coords[:, 1].astype(float)

    logger.info("Building SpaGCN adjacency matrix ...")
    adj = SpaGCN.calculate_adj_matrix(
        x=x_pixel, y=y_pixel, histology=False,
    )

    l_value = SpaGCN.search_l(0.5, adj, start=0.01, end=1000, tol=0.01, max_run=100)

    r_seed = 100
    clf = SpaGCN.SpaGCN()
    clf.set_l(l_value)
    clf.train(
        adata,
        adj,
        num_pcs=50,
        init_spa=True,
        init="louvain",
        res=0.4,
        tol=5e-3,
        lr=0.05,
        max_epochs=200,
        n_clusters=n_domains,
    )

    y_pred, prob = clf.predict()
    adata.obs["spatial_domain"] = pd.Categorical(y_pred.astype(str))

    refined = SpaGCN.refine(
        sample_id=adata.obs.index.tolist(),
        pred=y_pred,
        dis=adj,
        shape="hexagon",
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

    Note: STAGATE trains best on HVG-filtered data. If the input contains a
    ``highly_variable`` column in ``adata.var``, only HVGs are used for the
    autoencoder, reducing noise and training time (per Dong & Zhang, 2022).
    """
    from omicsclaw.spatial.dependency_manager import require

    require("STAGATE_pyG", feature="STAGATE spatial domain identification")
    require("torch", feature="STAGATE (PyTorch backend)")

    import torch
    import STAGATE_pyG

    logger.info("Running STAGATE (rad_cutoff=%.1f, n_domains=%d) ...", rad_cutoff, n_domains)

    # STAGATE official tutorial recommends using HVG subset for training.
    # Using the full gene matrix introduces noise and slows convergence.
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

    embedding = adata_work.obsm["STAGATE"]
    gmm = GaussianMixture(
        n_components=n_domains,
        covariance_type="tied",
        random_state=random_seed,
    )
    labels = gmm.fit_predict(embedding)

    adata.obs["spatial_domain"] = pd.Categorical(labels.astype(str))
    adata.obsm["X_stagate"] = embedding

    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("STAGATE domains: %d (requested %d)", actual_n, n_domains)

    return {
        "method": "stagate",
        "n_domains": actual_n,
        "n_domains_requested": n_domains,
        "rad_cutoff": rad_cutoff,
        "clustering": "gmm_tied",
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

    Uses graph neural networks with contrastive learning to learn embeddings
    that preserve both gene expression patterns and spatial relationships.
    Requires the GraphST package and PyTorch.

    Important: GraphST.preprocess() internally performs log1p + normalize +
    scale + HVG selection (top 3000). If the input ``adata.X`` is already
    log-normalized, passing it directly would cause a **double log-transform**.
    This function therefore restores raw counts from ``adata.raw`` (if
    available) before calling the GraphST pipeline, following the official
    tutorial workflow (Long et al., Nature Communications 2023).
    """
    from omicsclaw.spatial.dependency_manager import require

    require("GraphST", feature="GraphST spatial domain identification")
    require("torch", feature="GraphST (PyTorch backend)")

    import torch
    from GraphST import GraphST as GraphSTModule

    logger.info("Running GraphST (n_domains=%d) ...", n_domains)

    # GraphST.preprocess() does: log1p → normalize_total → scale → HVG(3000).
    # If adata.X is already log-normalized (from spatial-preprocess), we must
    # restore raw counts to avoid double log-transform.
    if adata.raw is not None:
        logger.info(
            "Restoring raw counts from adata.raw for GraphST "
            "(avoids double log-transform)"
        )
        adata_work = adata.raw.to_adata().copy()
        # Carry over spatial coordinates from the processed object
        spatial_key = get_spatial_key(adata)
        if spatial_key and spatial_key in adata.obsm:
            adata_work.obsm[spatial_key] = adata.obsm[spatial_key]
        if "spatial" not in adata_work.obsm and spatial_key and spatial_key != "spatial":
            adata_work.obsm["spatial"] = adata.obsm[spatial_key]
    else:
        logger.warning(
            "adata.raw not found — using adata.X directly. If adata.X is "
            "already log-normalized, GraphST results may be suboptimal due "
            "to double log-transform in GraphST.preprocess()."
        )
        adata_work = adata.copy()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Follow official GraphST API: preprocess → construct_interaction → train
    GraphSTModule.preprocess(adata_work)
    GraphSTModule.construct_interaction(adata_work)

    from GraphST.GraphST import GraphST as GraphSTModel

    model = GraphSTModel(adata_work, device=device, random_seed=random_seed)
    adata_work = model.train()

    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture

    pca = PCA(n_components=20, random_state=42)
    embedding = pca.fit_transform(adata_work.obsm["emb"])

    gmm = GaussianMixture(
        n_components=n_domains,
        covariance_type="tied",
        random_state=random_seed,
    )
    labels = gmm.fit_predict(embedding)

    adata.obs["spatial_domain"] = pd.Categorical(labels.astype(str))
    adata.obsm["X_graphst"] = adata_work.obsm["emb"]

    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("GraphST domains: %d (requested %d)", actual_n, n_domains)

    return {
        "method": "graphst",
        "n_domains": actual_n,
        "n_domains_requested": n_domains,
        "clustering": "gmm_tied",
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
    azimuthal Gabor filters. Unlike deep learning methods, BANKSY uses
    explicit mathematical feature construction for interpretability.

    Note: BANKSY official tutorial recommends z-scoring gene expression
    before neighbourhood feature construction so that high-expression
    genes do not dominate the neighbourhood average. This function
    applies ``sc.pp.scale()`` on a working copy before calling BANKSY.
    """
    from omicsclaw.spatial.dependency_manager import require

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

    # BANKSY recommends z-scoring gene expression before neighbourhood
    # feature construction (prabhakarlab/Banksy_py docs).  Without this,
    # genes with large absolute expression values dominate the
    # neighbourhood-averaged features and Gabor filter responses.
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
        adata_work,
        banksy_dict,
        lambda_list=[lambda_param],
        max_m=max_m,
        verbose=False,
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
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path) -> list[str]:
    """Generate spatial domain map and UMAP domain plot using the viz library."""
    figures = []
    spatial_key = get_spatial_key(adata)
    
    # viz library hardcodes adata.obsm["spatial"]
    if spatial_key and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm[spatial_key]

    domain_col = "spatial_domain" if "spatial_domain" in adata.obs.columns else None
    if domain_col is None:
        logger.warning("No 'spatial_domain' column found; skipping domain figures")
        return figures

    # 1. Spatial scatter coloured by domain
    if spatial_key is not None:
        try:
            fig = plot_features(
                adata,
                VizParams(
                    feature=domain_col,
                    basis="spatial",
                    colormap="tab20",
                    title="Spatial Domains",
                    show_legend=True,
                ),
            )
            p = save_figure(fig, output_dir, "spatial_domains.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate spatial domain figure: %s", exc)

    # 2. UMAP coloured by domain
    if "X_umap" not in adata.obsm:
        try:
            sc.tl.umap(adata)
        except Exception as exc:
            logger.warning("Could not compute UMAP: %s", exc)

    if "X_umap" in adata.obsm:
        try:
            fig = plot_features(
                adata,
                VizParams(
                    feature=domain_col,
                    basis="umap",
                    colormap="tab20",
                    title="UMAP — Spatial Domains",
                    show_legend=True,
                ),
            )
            p = save_figure(fig, output_dir, "umap_domains.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate UMAP domain figure: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write report.md, result.json, tables, reproducibility."""

    header = generate_report_header(
        title="Spatial Domain Identification Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Domains identified": str(summary["n_domains"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Domains identified**: {summary['n_domains']}",
    ]
    if "resolution" in summary:
        body_lines.append(f"- **Leiden resolution**: {summary['resolution']}")
    if "n_domains_requested" in summary:
        body_lines.append(f"- **Domains requested**: {summary['n_domains_requested']}")

    body_lines.extend([
        "",
        "### Domain sizes\n",
        "| Domain | Cells | Proportion |",
        "|--------|-------|------------|",
    ])

    total_cells = sum(summary["domain_counts"].values())
    for domain, count in sorted(
        summary["domain_counts"].items(),
        key=lambda x: int(x[0]) if x[0].isdigit() else x[0],
    ):
        pct = count / total_cells * 100 if total_cells > 0 else 0
        body_lines.append(f"| {domain} | {count} | {pct:.1f}% |")

    body_lines.append("")
    body_lines.append("## Parameters\n")
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer

    report_path = output_dir / "report.md"
    report_path.write_text(report)
    logger.info("Wrote %s", report_path)

    # result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data={"params": params, **summary},
        input_checksum=checksum,
    )

    # tables/domain_summary.csv
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    rows = []
    for domain, count in summary["domain_counts"].items():
        pct = count / total_cells * 100 if total_cells > 0 else 0
        rows.append({"domain": domain, "n_cells": count, "proportion": round(pct, 2)})
    df = pd.DataFrame(rows)
    df.to_csv(tables_dir / "domain_summary.csv", index=False)

    # reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_domains.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore

    env_lines = []
    for pkg in ["scanpy", "anndata", "squidpy", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data():
    """Load the built-in demo dataset."""
    demo_path = _PROJECT_ROOT / "examples" / "demo_visium.h5ad"
    if demo_path.exists():
        return sc.read_h5ad(demo_path), str(demo_path)

    logger.info("Demo file not found, generating synthetic data")
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
    from generate_demo_data import generate_demo_visium

    adata = generate_demo_visium()
    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _dispatch_method(method: str, adata, args) -> dict:
    """Route to the correct domain identification function."""
    n_domains = args.n_domains or 7

    if method == "leiden":
        return identify_domains_leiden(
            adata,
            resolution=args.resolution,
            spatial_weight=args.spatial_weight,
        )
    elif method == "louvain":
        return identify_domains_louvain(adata, resolution=args.resolution)
    elif method == "spagcn":
        return identify_domains_spagcn(adata, n_domains=n_domains)
    elif method == "stagate":
        return identify_domains_stagate(
            adata, n_domains=n_domains, rad_cutoff=args.rad_cutoff,
        )
    elif method == "graphst":
        return identify_domains_graphst(adata, n_domains=n_domains)
    elif method == "banksy":
        return identify_domains_banksy(
            adata,
            resolution=args.resolution,
            lambda_param=args.lambda_param,
        )
    else:
        raise ValueError(f"Unknown method: {method}. Choose from {SUPPORTED_METHODS}")


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Domains — multi-method tissue region identification",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method",
        choices=list(SUPPORTED_METHODS),
        default="leiden",
        help=f"Domain identification method (default: leiden). Options: {', '.join(SUPPORTED_METHODS)}",
    )
    parser.add_argument("--n-domains", type=int, default=None,
                        help="Target number of domains (for spagcn/stagate/graphst/banksy)")
    parser.add_argument("--resolution", type=float, default=1.0,
                        help="Clustering resolution for leiden/louvain/banksy (default: 1.0)")
    parser.add_argument("--spatial-weight", type=float, default=0.3,
                        help="Weight of spatial graph in leiden (0.0-1.0, default: 0.3)")
    parser.add_argument("--rad-cutoff", type=float, default=50.0,
                        help="STAGATE radius cutoff for spatial network (default: 50.0)")
    parser.add_argument("--lambda-param", type=float, default=0.2,
                        help="BANKSY spatial regularization parameter (default: 0.2)")
    parser.add_argument("--refine", action="store_true", default=False,
                        help="Apply spatial KNN refinement to domain labels")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
        if "X_pca" not in adata.obsm:
            raise ValueError(
                "Input data is missing required preprocessing. "
                "Expected 'X_pca' in adata.obsm but not found. "
                "This data appears to be raw/unprocessed."
            )
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    summary = _dispatch_method(args.method, adata, args)

    if args.refine:
        logger.info("Applying spatial KNN refinement ...")
        refined = refine_spatial_domains(adata)
        adata.obs["spatial_domain"] = pd.Categorical(refined)
        summary["domain_counts"] = adata.obs["spatial_domain"].value_counts().to_dict()
        summary["n_domains"] = adata.obs["spatial_domain"].nunique()
        summary["refined"] = True

    params = {
        "method": args.method,
        "resolution": args.resolution,
        "spatial_weight": args.spatial_weight,
        "refine": args.refine,
    }
    if args.n_domains is not None:
        params["n_domains"] = args.n_domains
    if args.method == "stagate":
        params["rad_cutoff"] = args.rad_cutoff
    if args.method == "banksy":
        params["lambda_param"] = args.lambda_param

    generate_figures(adata, output_dir)
    write_report(output_dir, summary, input_file, params)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params=params,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(f"Domain identification complete: {summary['n_domains']} domains ({summary['method']})")


if __name__ == "__main__":
    main()
