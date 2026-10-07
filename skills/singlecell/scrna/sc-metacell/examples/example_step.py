# %% [markdown]
# Build KMeans metacells on PBMC3k PCA. With no counts layer, aggregates are means of X.
# This groups cells, not biological replicates; the output is not summed pseudobulk counts.
# Reads pbmc3k_processed. Calls sc-metacell: metacells and output helpers.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

aggregation = load_skill("sc-metacell")
adata = load_demo("pbmc3k_processed")
metacells = aggregation.metacells(adata, method="kmeans", n_metacells=30, random_state=0)

# %%
write_output(aggregation.metacell_summary(metacells), "tables/metacell_summary.csv")
write_output(aggregation.cell_to_metacell(adata), "tables/cell_to_metacell.csv")
write_output(aggregation.size_distribution_figure(metacells), "figures/metacell_sizes.png")
write_output(metacells, "intermediate/metacells.h5ad")
assert metacells.n_obs == 30
assert metacells.obs["n_cells"].sum() == adata.n_obs
assert adata.obs["metacell"].nunique() == 30
