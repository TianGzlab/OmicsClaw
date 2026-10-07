# %% [markdown]
# Pseudotime on simulated expression domains; this is not a biological lineage.

# %%
import matplotlib.pyplot as plt
import numpy as np
import scanpy as sc
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill("spatial-trajectory")
adata = load_demo("spatial_synthetic")
sc.pp.normalize_total(adata, target_sum=10000)
sc.pp.log1p(adata)
sc.pp.pca(adata, n_comps=15, random_state=0)
sc.pp.neighbors(adata, random_state=0)

# %%
library.trajectory(adata, root_cell=str(adata.obs_names[0]))
assert adata.obs["dpt_pseudotime"].iloc[0] == 0
assert np.isfinite(adata.obs["dpt_pseudotime"]).any()
write_output(library.pseudotime_table(adata), "tables/pseudotime.csv")
write_output(library.trajectory_genes(adata), "tables/trajectory_genes.csv")
write_output(adata, "intermediate/trajectory.h5ad")
figure = library.pseudotime_figure(adata)
write_output(figure, "figures/pseudotime.png")
plt.close(figure)
