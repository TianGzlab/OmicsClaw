# Output contract

`pseudotime` returns a new AnnData with `obs["pseudotime"]` and the
backend's original pseudotime column. The input is unchanged.
`run_info` records the method, inference representation, display embedding
and root. A root is a user assumption about direction, not inferred truth.
Table and figure functions return objects without writing files.

The CLI writes `processed.h5ad`, `tables/pseudotime_cells.csv`,
`tables/trajectory_genes.csv`, `tables/trajectory_summary.csv`,
`report.md` and `result.json`.
Fate-probability tables appear only for backends that produce them.
R curves are retained when returned by Slingshot or Monocle3; those
backends require their separate R packages. Plots and plot-source tables
depend on available embeddings and successful rendering. R bridge
intermediates are temporary, not unconditional deliverables.
