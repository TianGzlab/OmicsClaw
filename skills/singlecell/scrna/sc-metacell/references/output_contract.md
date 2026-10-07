# Output contract

`metacells` annotates the input's `obs["metacell"]` and returns a new
AnnData of mean-expression aggregates. `X` and `layers["mean_expression"]`
contain averages, not count sums. `obs` includes cell counts and dominant
labels. `run_info` records the requested and executed methods, fallback
reason, input matrix source and seed.

The CLI's `processed.h5ad` is the original cells with assignments;
`metacells_annotated.h5ad` is a compatibility alias.
Aggregates are written separately to `tables/metacells.h5ad`.
`tables/cell_to_metacell.csv` maps cells to aggregates and
`tables/metacell_summary.csv` describes aggregates.
`result.json.data.run_info` records any missing-SEACells fallback to
KMeans. Grouping is not sample-aware; this is not sample-level pseudobulk.
Embedding and R-enhanced figures depend on available embeddings/backends.
