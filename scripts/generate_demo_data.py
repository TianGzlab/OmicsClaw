#!/usr/bin/env python3
"""Generate synthetic spatial transcriptomics demo data.

Creates a minimal Visium-like dataset with 200 spots, 100 genes,
3 spatial domains, and spatial coordinates on a grid.
"""

from __future__ import annotations

from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd


def generate_demo_visium(
    n_spots: int = 200,
    n_genes: int = 100,
    n_domains: int = 3,
    seed: int = 42,
) -> ad.AnnData:
    """Generate a synthetic spatial transcriptomics dataset."""
    rng = np.random.default_rng(seed)

    # Spatial coordinates on a grid
    side = int(np.ceil(np.sqrt(n_spots)))
    coords = np.array(
        [(x, y) for x in range(side) for y in range(side)]
    )[:n_spots].astype(np.float64)

    # Assign spatial domains based on position
    domain_labels = []
    for x, y in coords:
        if x < side / 3:
            domain_labels.append("domain_0")
        elif x < 2 * side / 3:
            domain_labels.append("domain_1")
        else:
            domain_labels.append("domain_2")

    # Gene names
    gene_names = [f"Gene_{i:03d}" for i in range(n_genes)]

    # Domain-specific marker genes (first 10 genes per domain)
    marker_ranges = {
        "domain_0": (0, 10),
        "domain_1": (10, 20),
        "domain_2": (20, 30),
    }

    # Generate count matrix with domain-specific patterns
    counts = rng.poisson(lam=2, size=(n_spots, n_genes)).astype(np.float32)
    for i, domain in enumerate(domain_labels):
        lo, hi = marker_ranges[domain]
        counts[i, lo:hi] += rng.poisson(lam=15, size=hi - lo).astype(np.float32)

    # Add mitochondrial genes (last 5)
    for i in range(n_genes - 5, n_genes):
        gene_names[i] = f"MT-{gene_names[i]}"
    mt_fraction = rng.uniform(0.01, 0.08, size=n_spots)
    for i in range(n_spots):
        mt_counts = int(counts[i].sum() * mt_fraction[i])
        mt_idx = rng.choice(range(n_genes - 5, n_genes))
        counts[i, mt_idx] += mt_counts

    # Build AnnData
    obs = pd.DataFrame(
        {"domain_ground_truth": domain_labels},
        index=[f"spot_{i:04d}" for i in range(n_spots)],
    )
    var = pd.DataFrame(index=gene_names)
    adata = ad.AnnData(X=counts, obs=obs, var=var)
    adata.obsm["spatial"] = coords

    return adata


def main():
    output_dir = Path(__file__).resolve().parent.parent / "examples"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "demo_visium.h5ad"

    adata = generate_demo_visium()
    adata.write_h5ad(path)
    print(f"Generated demo data: {path}")
    print(f"  {adata.n_obs} spots x {adata.n_vars} genes")
    print(f"  Domains: {adata.obs['domain_ground_truth'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
