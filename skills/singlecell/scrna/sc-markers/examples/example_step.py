# %% [markdown]
# Rank markers for the PBMC68k labels using its log-normalized raw snapshot.
# Reads pbmc68k_reduced.
# Calls sc-markers: find_markers, top_markers, marker_dotplot_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

markers = load_skill("sc-markers")
adata = load_demo("pbmc68k_reduced").raw.to_adata()

# %%
table = markers.find_markers(adata, groupby="bulk_labels")
top = markers.top_markers(table)
write_output(table, "tables/markers_all.csv")
write_output(top, "tables/markers_top.csv")
write_output(markers.marker_dotplot_figure(adata, table, groupby="bulk_labels"),
             "figures/markers_dotplot.png")

# %%
assert not top.empty
assert top["group"].nunique() == adata.obs["bulk_labels"].nunique()
assert set(top["names"]).issubset(adata.var_names)
assert {"CD79A", "MS4A1"} & set(top.loc[top["group"].astype(str).str.contains("B"), "names"])
