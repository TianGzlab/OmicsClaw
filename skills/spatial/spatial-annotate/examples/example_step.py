"""Annotate PBMC clusters from measured marker expression."""
from skills._sdk.notebook import load_demo, load_skill, write_output

data = load_demo("pbmc3k_processed").raw.to_adata()
library = load_skill("spatial-annotate")
library.annotate(data, cluster_key="louvain", n_marker_genes=50)
assert library.run_info(data)["n_cell_types"] >= 3
write_output(library.cell_type_counts(data), "tables/annotation_summary.csv")
