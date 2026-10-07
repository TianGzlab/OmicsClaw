# %% [markdown]
# Exercise file conversion and provenance with synthetic upstream outputs.
# This does not align FASTQ reads or validate ST-Pipeline installation.

# %%
import anndata as ad
import numpy as np
from skills._sdk.notebook import run_cli, write_output

output = run_cli("spatial-raw-processing", "--demo", timeout=180)
adata = ad.read_h5ad(output / "raw_counts.h5ad")
assert adata.n_obs > 0 and adata.n_vars > 0
assert "spatial" in adata.obsm and "counts" in adata.layers
matrix = adata.X.toarray() if hasattr(adata.X, "toarray") else adata.X
assert np.isfinite(matrix).all() and (matrix >= 0).all()
np.testing.assert_allclose(matrix, np.round(matrix))
write_output(adata, "intermediate/raw_counts.h5ad")
