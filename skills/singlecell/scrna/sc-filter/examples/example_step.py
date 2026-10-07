# %% [markdown]
# Filter PBMC3k with the PBMC preset and compare cell identities with Scanpy's processed dataset.
# Reads pbmc3k_raw and pbmc3k_processed.
# Calls sc-qc: calculate_qc; sc-filter: filter_cells, filter_summary, filter_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

qc = load_skill("sc-qc")
filtering = load_skill("sc-filter")
before = qc.calculate_qc(load_demo("pbmc3k_raw"))

# %%
after = filtering.filter_cells(before, tissue="pbmc")
write_output(filtering.filter_summary(after), "tables/filter_summary.csv")
write_output(filtering.filter_figure(before, after), "figures/filter_retention.png")
write_output(after, "intermediate/adata_filtered.h5ad")

# %%
reference = load_demo("pbmc3k_processed")
assert after.n_obs == 2638
assert after.obs_names.equals(reference.obs_names)
