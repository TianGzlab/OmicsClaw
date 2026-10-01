# %% [markdown]
# Cluster PBMC3k with sc-clustering's defaults and check the result.
# Reads the pbmc3k_processed demo dataset.
# Calls sc-clustering: cluster, cluster_summary, embedding_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

clustering = load_skill("sc-clustering")
adata = load_demo("pbmc3k_processed")

# %%
adata = clustering.cluster(adata, resolution=1.0, random_state=0)
summary = clustering.cluster_summary(adata, key="leiden")
write_output(summary, "tables/cluster_summary.csv")
write_output(clustering.embedding_figure(adata, color="leiden"), "figures/umap_leiden.png")

# %%
assert adata.obs["leiden"].nunique() >= 4
assert int(summary["n_cells"].sum()) == adata.n_obs
