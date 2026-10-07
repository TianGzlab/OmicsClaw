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
Tiny inputs and graph/latent-time failures raise errors. Neither the API
nor CLI substitutes arithmetic velocities, identity graphs or uniform
latent-time sequences. A successful `run_info` records
`placeholder_fallback_used=false` and `fit_validation_performed=false`;
numerically complete output still requires biological interpretation.
The kinetic-simulation example uses 40 genes for fitted velocity.

On success the standalone CLI closes its own workers and exits zero;
it does not signal the notebook kernel's process group.
