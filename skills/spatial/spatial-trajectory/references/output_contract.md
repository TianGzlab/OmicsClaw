# Output contract

## Function library

The computation returns the same AnnData. Table accessors return DataFrames;
plot functions return Figures without writing files. Diagnostics are a JSON string
in `uns['omicsclaw_spatial_trajectory_run']`; `run_info(keep=False)` removes it.

DPT and CellRank write obs['dpt_pseudotime'] and integer uns['iroot']. Palantir writes obs['palantir_pseudotime'], obs['palantir_entropy'] and optional branch probabilities. CLI gallery annotations are additional outputs, not requirements of the function library.

## CLI artifacts

`processed.h5ad`, `report.md` and `result.json` are written after a successful run.
Commands and R plotting helpers live under `reproducibility/`.
That directory also contains requirements.txt and environment.txt.

The summary and gene tables are always written, though the gene table can be empty. Terminal-state, driver and fate-probability tables need the corresponding backend results. Terminal states also get a method-named alias. The Palantir branch table is written only for nonempty branch probabilities.

- `tables/trajectory_summary.csv`
- `tables/trajectory_cluster_summary.csv`
- `tables/trajectory_genes.csv`
- `tables/trajectory_terminal_states.csv`
- `tables/trajectory_driver_genes.csv`
- `tables/trajectory_fate_probabilities_wide.csv`
- `tables/palantir_branch_probs.csv`
- `tables/cellrank_driver_genes.csv`

Figure-ready summaries and coordinate tables live under `figure_data/`, with
`figure_data/manifest.json`. They are not additional files under `tables/`.
The gallery records rendered/skipped artifacts in `figures/manifest.json`.
A renderer can skip an otherwise eligible plot if its backend cannot render it.

| Figure | Required result |
|---|---|
| `figures/cellrank_fate_circular.png` | CellRank fate probabilities; individual renderers may skip unavailable inputs |
| `figures/cellrank_fate_heatmap.png` | CellRank fate probabilities; individual renderers may skip unavailable inputs |
| `figures/cellrank_fate_map.png` | CellRank fate probabilities; individual renderers may skip unavailable inputs |
| `figures/cellrank_gene_trends.png` | CellRank lineage/driver results |
| `figures/trajectory_cluster_summary.png` | resolved cluster labels |
| `figures/trajectory_diffmap.png` | diffusion coordinates |
| `figures/trajectory_entropy_distribution.png` | entropy values |
| `figures/trajectory_fate_probability_distribution.png` | fate-probability values |
| `figures/trajectory_genes_barplot.png` | nonempty trajectory genes |
| `figures/trajectory_pseudotime_distribution.png` | pseudotime values |
| `figures/trajectory_pseudotime_embedding.png` | UMAP coordinates and pseudotime |
| `figures/trajectory_pseudotime_spatial.png` | spatial coordinates and pseudotime |
