# %% [markdown]
# Merge two halves of PBMC3k as demonstration samples, not biological replicates.
# Reads pbmc3k_raw and calls sc-multi-count: merge_samples, per_sample_summary,
# sample_composition_figure. Preserve every cell and the total count sum.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

adata = load_demo("pbmc3k_raw")
library = load_skill("sc-multi-count")
midpoint = adata.n_obs // 2
merged = library.merge_samples([adata[:midpoint], adata[midpoint:]], sample_ids=["first", "second"])
assert merged.n_obs == adata.n_obs
assert float(merged.X.sum()) == float(adata.X.sum())
assert set(merged.obs["sample_id"]) == {"first", "second"}
write_output(merged, "intermediate/merged.h5ad")
write_output(library.per_sample_summary(merged), "tables/samples.csv")
write_output(library.sample_composition_figure(merged), "figures/samples.png")
