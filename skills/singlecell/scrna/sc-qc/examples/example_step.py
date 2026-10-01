# %% [markdown]
# QC metrics for PBMC3k with sc-qc's defaults, and a check of the result.
# Reads the pbmc3k_raw demo dataset.
# Calls sc-qc: calculate_qc, qc_summary, qc_metrics_table, qc_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

qc = load_skill("sc-qc")
adata = load_demo("pbmc3k_raw")

# %%
# species "human": PBMC3k is a human sample, so the MT- and RPS/RPL prefixes apply.
adata = qc.calculate_qc(adata, species="human")
summary = qc.qc_summary(adata)
write_output(summary, "tables/qc_metrics_summary.csv")
write_output(qc.qc_metrics_table(adata), "tables/qc_metrics_per_cell.csv")
write_output(qc.qc_figure(adata), "figures/qc_histograms.png")
write_output(adata, "intermediate/adata_qc.h5ad")

# %%
assert adata.n_obs == 2700
assert {"n_genes_by_counts", "total_counts", "pct_counts_mt"} <= set(summary["metric"])
assert 0 < float(summary.set_index("metric").loc["pct_counts_mt", "median"]) < 10
