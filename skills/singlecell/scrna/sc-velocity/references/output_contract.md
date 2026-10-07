# Output contract

`velocity` mutates its AnnData and can remove genes during filtering.
It requires aligned `spliced` and `unspliced` layers.
Diagnostics and table helpers return objects; no API function exits the
process or writes output files.

The CLI writes `processed.h5ad` with compatibility alias
`adata_with_velocity.h5ad`, `tables/velocity_summary.csv`,
`tables/velocity_cells.csv`, `tables/top_velocity_genes.csv`,
`report.md` and `result.json`.
Velocity/latent-time figures are conditional on their embeddings and
successful rendering; R-enhanced figures are optional.
Existing tiny-data arithmetic, identity-graph and latent-time fallbacks
remain compatibility behavior. Inspect diagnostics before interpreting
these outputs as biological dynamics. The kinetic-simulation example
uses 40 genes to exercise fitted velocity rather than the tiny-data path.

On success the standalone CLI closes its own workers and exits zero;
it does not signal the notebook kernel's process group.
