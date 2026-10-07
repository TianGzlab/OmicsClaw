# %% [markdown]
# Illustrate fixed-fraction subtraction on PBMC3k counts.
# There are no empty droplets here; the mean cell profile is only an approximation.
# Reads pbmc3k_raw. Calls sc-ambient-removal: remove_ambient and output helpers.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

ambient = load_skill("sc-ambient-removal")
adata = load_demo("pbmc3k_raw")
shape = adata.shape

# %%
ambient.remove_ambient(adata, contamination=0.05)
comparison = ambient.counts_comparison_table(adata)
write_output(ambient.correction_summary(adata), "tables/correction_summary.csv")
write_output(comparison, "tables/counts_comparison.csv")
write_output(ambient.correction_figure(adata), "figures/counts_comparison.png")
write_output(adata, "intermediate/adata_corrected.h5ad")
assert adata.shape == shape
assert adata.X.min() >= 0
assert (comparison["counts_after"] <= comparison["counts_before"]).all()
assert comparison["counts_after"].sum() < comparison["counts_before"].sum()
