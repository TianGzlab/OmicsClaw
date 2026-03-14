#!/usr/bin/env python3
"""Download standard single-cell demo dataset."""

import scanpy as sc

# Download PBMC3k dataset (standard benchmark)
adata = sc.datasets.pbmc3k()

# Save to examples folder
output_path = "../examples/pbmc3k.h5ad"
adata.write_h5ad(output_path)

print(f"✓ Downloaded PBMC3k dataset: {adata.n_obs} cells × {adata.n_vars} genes")
print(f"✓ Saved to: {output_path}")
