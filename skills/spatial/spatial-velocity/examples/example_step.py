# %% [markdown]
# Simulated spliced/unspliced counts test the workflow, not biological dynamics.

# %%
import matplotlib.pyplot as plt
import numpy as np
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill("spatial-velocity")
adata = load_demo("spatial_synthetic")
counts = adata.X.toarray() if hasattr(adata.X, "toarray") else np.asarray(adata.X)
rng = np.random.default_rng(0)
adata.layers["spliced"] = rng.poisson(counts * 0.8).astype(float)
adata.layers["unspliced"] = rng.poisson(counts * 0.2 + 1).astype(float)
adata.obs["leiden"] = adata.obs["domain_ground_truth"].astype("category")

# %%
library.velocity(adata, random_state=0)
table = library.cell_metrics(adata)
assert len(table) == adata.n_obs
assert np.isfinite(table["velocity_speed"]).all()
assert (table["velocity_speed"] >= 0).all()
# scVelo's unseeded pseudotime remains in the AnnData; compare stable metrics here.
write_output(table.drop(columns="velocity_pseudotime", errors="ignore"), "tables/velocity_cells.csv")
write_output(library.gene_metrics(adata), "tables/velocity_genes.csv")
write_output(adata, "intermediate/velocity.h5ad")
figure = library.velocity_figure(adata)
write_output(figure, "figures/velocity.png")
plt.close(figure)
