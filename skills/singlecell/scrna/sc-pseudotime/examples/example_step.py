# %% [markdown]
# Demonstrate DPT on PBMC3k; this is not a validated differentiation trajectory.
# The largest cluster is an arbitrary demonstration root, not a progenitor annotation.
# Reads pbmc3k_processed. Calls sc-pseudotime: pseudotime and output helpers.

# %%
import numpy as np
import scanpy as sc
from skills._sdk.notebook import load_demo, load_skill, write_output

trajectory = load_skill("sc-pseudotime")
adata = load_demo("pbmc3k_processed").raw.to_adata()
sc.pp.pca(adata, n_comps=30, random_state=0)
root = str(adata.obs["louvain"].value_counts().idxmax())

# %%
result = trajectory.pseudotime(adata, method="dpt", cluster_key="louvain",
                               root_cluster=root, use_rep="X_pca", n_pcs=30)
write_output(trajectory.pseudotime_table(result), "tables/pseudotime.csv")
write_output(trajectory.trajectory_genes(result, n_genes=20), "tables/trajectory_genes.csv")
write_output(trajectory.pseudotime_figure(result), "figures/pseudotime.png")
write_output(result, "intermediate/adata_pseudotime.h5ad")
assert trajectory.run_info(result)["use_rep"] == "X_pca"
assert np.isfinite(result.obs["pseudotime"]).all()
assert result.obs["pseudotime"].max() > result.obs["pseudotime"].min()
