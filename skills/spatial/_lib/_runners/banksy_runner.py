"""BANKSY runner script. Runs inside the `omicsclaw_banksy` sub-env.

Reads --input (.h5ad), runs BANKSY domain identification with the same
algorithm as skills/spatial/_lib/domains.py:identify_domains_banksy
(non-negative library-size normalization, optional HVG subsetting,
smart routing between fixed-n_domains GMM/KMeans and resolution-based
Leiden), writes --output (.h5ad) with results in adata.obs[
'spatial_domain'], adata.obsm['X_banksy_pca'], and adata.uns[
'banksy_meta'].

Do NOT import OmicsClaw modules here — the sub-env does not have
omicsclaw installed, only the BANKSY-specific deps from
environments/banksy.yml.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Optional

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
import scipy.sparse as sp
from banksy.embed_banksy import generate_banksy_matrix
from banksy.initialize_banksy import initialize_banksy

logger = logging.getLogger("banksy_runner")
logging.basicConfig(level=logging.INFO, format="[banksy_runner] %(message)s")


def _get_spatial_key(adata) -> Optional[str]:
    """Find the spatial coordinate key in adata.obsm."""
    for k in ("spatial", "X_spatial", "spatial_coords"):
        if k in adata.obsm:
            return k
    return None


def run_banksy(
    adata,
    *,
    n_domains: int | None = None,
    resolution: float = 0.7,
    lambda_param: float = 0.2,
    num_neighbours: int = 15,
    max_m: int = 1,
    pca_dims: int = 20,
) -> dict:
    """Port of skills/spatial/_lib/domains.py:identify_domains_banksy.

    BANKSY — spatial feature augmentation for domain identification.

    Augments gene expression with neighborhood-averaged expression and
    azimuthal Gabor filters.  BANKSY expects **non-negative normalized
    expression** (library-size normalized, *not* z-scored).  The function
    restores raw counts from ``adata.layers["counts"]`` or ``adata.raw``
    and applies ``normalize_total`` without ``log1p`` so that all values
    remain >= 0.

    Mutates adata in place (sets adata.obs['spatial_domain'] and
    adata.obsm['X_banksy_pca']). Returns metadata dict.
    """
    logger.info(
        "Running BANKSY (lambda=%.2f, n_domains=%s, resolution=%.2f) ...",
        lambda_param, n_domains, resolution,
    )

    # --- Prepare non-negative normalized expression -------------------------
    # BANKSY requires non-negative values; z-score scaling (sc.pp.scale)
    # introduces negatives and must NOT be used here.
    adata_work = adata.copy()

    if "counts" in adata.layers:
        logger.info(
            "Restoring raw counts from adata.layers['counts'] and applying "
            "library-size normalization (non-negative) for BANKSY"
        )
        adata_work.X = adata.layers["counts"].copy()
        sc.pp.normalize_total(adata_work, target_sum=1e4)
    elif adata.raw is not None:
        logger.info(
            "Restoring raw counts from adata.raw and applying "
            "library-size normalization (non-negative) for BANKSY"
        )
        raw_ad = adata.raw.to_adata()
        adata_work.X = raw_ad.X.copy()
        sc.pp.normalize_total(adata_work, target_sum=1e4)
    else:
        # Fallback: use adata.X as-is but clip any negative values
        x = adata_work.X
        x_min = x.min() if not sp.issparse(x) else x.data.min() if x.nnz > 0 else 0.0
        if x_min < 0:
            logger.warning(
                "BANKSY expects non-negative expression but detected min=%.4f. "
                "Clipping negatives to 0. For best results, ensure "
                "adata.layers['counts'] or adata.raw contains raw counts.",
                x_min,
            )
            if sp.issparse(x):
                adata_work.X = x.maximum(0)
            else:
                adata_work.X = np.maximum(x, 0)
        else:
            logger.info("Using adata.X as-is for BANKSY (non-negative, min=%.4f)", x_min)

    # Dramatically accelerate memory and processing by stripping down to highly-variable genes
    if "highly_variable" in adata.var.columns and adata.var["highly_variable"].sum() > 0:
        n_hvg = adata.var["highly_variable"].sum()
        logger.info("Subsetting to %d HVGs to accelerate BANKSY matrix generation", n_hvg)
        adata_work = adata_work[:, adata.var["highly_variable"]].copy()
    else:
        logger.warning(
            "No HVG mask found. BANKSY will augment all %d genes, memory footprint may be extreme.",
            adata_work.n_vars,
        )

    spatial_key = _get_spatial_key(adata_work)
    if spatial_key is None:
        raise ValueError("BANKSY requires spatial coordinates in obsm")
    if spatial_key != "spatial":
        adata_work.obsm["spatial"] = adata_work.obsm[spatial_key]

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

    # Smart Routing: Exact cluster count vs Graph-based discovery
    if n_domains is not None and n_domains > 0:
        logger.info(
            "BANKSY: n_domains=%d specified, forcing extraction via tied-GMM fallback",
            n_domains,
        )
        from sklearn.mixture import GaussianMixture
        from sklearn.cluster import KMeans

        embedding = banksy_matrix.obsm["X_pca"]
        try:
            gmm = GaussianMixture(
                n_components=n_domains, covariance_type="tied",
                random_state=42, reg_covar=1e-3,
            )
            labels = gmm.fit_predict(embedding)
            cluster_name = "gmm_tied"
        except Exception as e:
            logger.warning("GMM failed (%s), shifting BANKSY segmentation to KMeans", e)
            kmeans = KMeans(n_clusters=n_domains, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embedding)
            cluster_name = "kmeans"

        banksy_matrix.obs["banksy_cluster"] = pd.Categorical(labels.astype(str))
    else:
        logger.info(
            "BANKSY: No fixed n_domains specified, running heuristic graph clustering (Leiden mode)"
        )
        sc.pp.neighbors(banksy_matrix, use_rep="X_pca", n_neighbors=num_neighbours)
        sc.tl.leiden(banksy_matrix, resolution=resolution, flavor="igraph", key_added="banksy_cluster")
        n_domains = banksy_matrix.obs["banksy_cluster"].nunique()
        cluster_name = "leiden"

    adata.obs["spatial_domain"] = banksy_matrix.obs["banksy_cluster"].values
    adata.obsm["X_banksy_pca"] = banksy_matrix.obsm["X_pca"]

    actual_n = adata.obs["spatial_domain"].nunique()
    logger.info("BANKSY domains identified: %d", actual_n)

    return {
        "method": "banksy",
        "n_domains": actual_n,
        "n_domains_requested": n_domains,
        "lambda": lambda_param,
        "clustering": cluster_name,
        "resolution": resolution,
        "num_neighbours": num_neighbours,
        "original_features": adata_work.n_vars,
        "banksy_features": banksy_matrix.n_vars,
        "domain_counts": adata.obs["spatial_domain"].value_counts().to_dict(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--params", default="{}")
    args = ap.parse_args()

    params = json.loads(args.params)

    adata = anndata.read_h5ad(args.input)

    metadata = run_banksy(
        adata,
        n_domains=params.get("n_domains"),
        resolution=float(params.get("resolution", 0.7)),
        lambda_param=float(params.get("lambda_param", 0.2)),
        num_neighbours=int(params.get("num_neighbours", 15)),
        max_m=int(params.get("max_m", 1)),
        pca_dims=int(params.get("pca_dims", 20)),
    )

    # Persist metadata for the main-env wrapper to retrieve.
    adata.uns["banksy_meta"] = metadata

    adata.write_h5ad(args.output, compression="gzip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
