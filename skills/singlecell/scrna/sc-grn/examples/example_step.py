# %% [markdown]
# Inspect TF-target correlation candidates in PBMC3k; this does not establish regulation.
# Mean target expression is reported explicitly and is not AUCell.
# Reads pbmc3k_processed. Calls sc-grn: infer_adjacencies, regulons_from_adjacencies and score helpers.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

grn = load_skill("sc-grn")
adata = load_demo("pbmc3k_processed").raw.to_adata()
tfs = ["SPI1", "IRF8", "STAT1", "JUN", "FOS", "GATA3"]
adjacencies = grn.infer_adjacencies(adata, tfs=tfs, method="correlation", n_top=20)
regulons = grn.regulons_from_adjacencies(adjacencies, n_top=20)
scores = grn.score_regulons(adata, regulons, method="mean")

# %%
write_output(adjacencies, "tables/adjacencies.csv")
write_output(scores, "tables/mean_target_expression.csv")
write_output(grn.regulon_heatmap_figure(scores, groups=adata.obs["louvain"]), "figures/regulon_means.png")
assert len(adjacencies) > 0
assert set(adjacencies["TF"]) <= set(tfs)
assert scores.attrs["is_aucell"] is False
assert scores.shape[0] == adata.n_obs
