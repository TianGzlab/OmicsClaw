# %% [markdown]
# Fit velocities to simulated splicing kinetics, not proportionally copied count layers.
# Reads velocity_simulation. Calls sc-velocity: velocity and output helpers.

# %%
import numpy as np
import scanpy as sc
from scipy import sparse
from skills._sdk.notebook import load_demo, load_skill, write_output

velocity = load_skill("sc-velocity")
adata = velocity.velocity(load_demo("velocity_simulation"), n_jobs=1, random_state=0)
sc.tl.umap(adata, random_state=0)

# %%
write_output(velocity.velocity_summary(adata), "tables/velocity_summary.csv")
write_output(velocity.top_velocity_genes(adata), "tables/top_velocity_genes.csv")
write_output(velocity.stream_figure(adata), "figures/velocity_stream.png")
write_output(adata, "intermediate/adata_velocity.h5ad")
diagnostics = velocity.velocity_diagnostics(adata)
assert not diagnostics["degenerate"]
assert diagnostics["n_velocity_genes"] > 0
assert np.isfinite(adata.layers["velocity"]).all()
assert velocity.run_info(adata)["placeholder_fallback_used"] is False
assert diagnostics["fit_validation_performed"] is False
graph = sparse.csr_matrix(adata.uns["velocity_graph"])
assert (graph - sparse.eye(adata.n_obs, format="csr")).nnz > 0
