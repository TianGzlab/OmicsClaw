# %% [markdown]
# Preprocess PBMC3k with sc-preprocessing's scanpy defaults and check the result.
# Reads the pbmc3k_raw demo dataset.
# Calls sc-preprocessing: preprocess, run_info, hvg_table, pca_variance_table, pca_variance_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

pre = load_skill("sc-preprocessing")
adata = load_demo("pbmc3k_raw")

# %%
# The defaults: scanpy method, min_genes 200, min_cells 3, max_mt_pct 20, 2000 HVGs, 50 PCs.
adata = pre.preprocess(adata, method="scanpy")
filtering = pre.run_info(adata)["filter_summary"]
write_output(filtering, "tables/filter_summary.json")
write_output(pre.hvg_table(adata, n_top=50), "tables/hvg_summary.csv")
write_output(pre.pca_variance_table(adata), "tables/pca_variance_ratio.csv")
write_output(pre.pca_variance_figure(adata), "figures/pca_variance.png")

# %%
assert 2000 < adata.n_obs < 2700
assert int(adata.var["highly_variable"].sum()) == 2000
assert adata.obsm["X_pca"].shape == (adata.n_obs, 50)
