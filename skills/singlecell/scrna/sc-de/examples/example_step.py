# %% [markdown]
# Wilcoxon markers for PBMC3k's louvain clusters, and a check of the result.
# Reads the pbmc3k_processed demo dataset.
# Calls sc-de: rank_genes, run_info, top_genes, volcano_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

de = load_skill("sc-de")
adata = load_demo("pbmc3k_processed")

# %%
table = de.rank_genes(adata, groupby="louvain", method="wilcoxon")
top = de.top_genes(table, n_top=10)
write_output(table, "tables/de_full.csv")
write_output(top, "tables/markers_top.csv")
write_output(de.volcano_figure(table, group="B cells"), "figures/volcano_b_cells.png")

# %%
assert de.run_info(adata)["summary"]["groupby"] == "louvain"
assert set(top["group"]) == set(adata.obs["louvain"].astype(str))
assert "MS4A1" in set(top.loc[top["group"] == "B cells", "names"])
