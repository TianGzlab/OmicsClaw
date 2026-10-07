# %% [markdown]
# Fit velocities to simulated splicing kinetics, not proportionally copied count layers.
# Reads velocity_simulation. Calls sc-velocity: velocity and output helpers.

# %%
import numpy as np
import scanpy as sc
import pandas as pd
from scipy import sparse
from scipy.stats import spearmanr
from skills._sdk.notebook import load_demo, load_skill, write_output

velocity = load_skill("sc-velocity")
source = load_demo("velocity_simulation")
source_genes = source.var_names.copy()
# The simulator's spliced-RNA derivative is beta * unspliced - gamma * spliced.
true_velocity = (source.layers["unspliced"] * source.var["true_beta"].to_numpy()
                 - source.layers["spliced"] * source.var["true_gamma"].to_numpy())
adata = velocity.velocity(source, n_jobs=1, random_state=0)
sc.tl.umap(adata, random_state=0)

# %%
truth = true_velocity[:, source_genes.get_indexer(adata.var_names)]
correlations = np.array([spearmanr(truth[:, i], adata.layers["velocity"][:, i]).statistic
                         for i in range(adata.n_vars)])
# This checks orientation on this synthetic screen, not biological fit accuracy.
assert np.isfinite(correlations).all(), "simulation kinetics: undefined direction correlation"
assert np.median(correlations) > 0.5, "simulation kinetics: velocity direction is wrong"
assert np.mean(correlations > 0) >= 0.75, "simulation kinetics: too many reversed gene velocities"
write_output(pd.DataFrame({"gene": adata.var_names, "direction_spearman": correlations}),
             "tables/kinetic_direction.csv")
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
