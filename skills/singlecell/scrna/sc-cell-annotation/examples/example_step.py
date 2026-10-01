# %% [markdown]
# Marker-based cell-type annotation of PBMC3k's louvain clusters, and a check of the result.
# Reads the pbmc3k_processed demo dataset (log-normalised, with louvain clusters and UMAP).
# Calls sc-cell-annotation: annotate, run_info, annotation_table, annotation_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

annotation = load_skill("sc-cell-annotation")
adata = load_demo("pbmc3k_processed")

# %%
# markers with the built-in human set: PBMC is blood, which the built-in set covers.
adata = annotation.annotate(adata, method="markers", cluster_key="louvain")
run = annotation.run_info(adata)
counts = annotation.annotation_table(adata, key="cell_type")
write_output(counts, "tables/cell_type_counts.csv")
write_output(run["summary"], "tables/annotation_run.json")
write_output(annotation.annotation_figure(adata, key="cell_type"), "figures/umap_cell_type.png")

# %%
assert run["summary"]["actual_method"] == "markers"
assert int(counts["n_cells"].sum()) == adata.n_obs
assert (counts["cell_type"] != "Unknown").sum() >= 4
