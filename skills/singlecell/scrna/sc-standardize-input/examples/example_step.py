# %% [markdown]
# Standardize PBMC3k using a preserved counts layer rather than normalized X.
# Reads pbmc3k_raw. Calls sc-standardize-input: standardize, run_info.

# %%
import numpy as np
from skills._sdk.notebook import load_demo, load_skill, write_output

standardizer = load_skill("sc-standardize-input")
original = load_demo("pbmc3k_raw")
original.layers["counts"] = original.X.copy()
original.X = original.X.copy()
original.X.data = np.log1p(original.X.data)

# %%
adata = standardizer.standardize(original, species="human")
info = standardizer.run_info(adata)
write_output(adata, "intermediate/adata_standardized.h5ad")
assert adata is not original
assert info["expression_source"] == "layers.counts"
assert (adata.X != original.layers["counts"]).nnz == 0
assert adata.shape == original.shape
assert adata.raw is not None
