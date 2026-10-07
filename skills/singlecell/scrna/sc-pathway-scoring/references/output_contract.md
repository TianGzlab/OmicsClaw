# Outputs

The Python API returns in-memory objects and figures. It does not create a
report directory. Examples persist selected objects with `write_output`.

The standalone CLI writes `processed.h5ad`, `report.md` and `result.json`.
Its plots are under `figures/`; plot source tables are under `figure_data/`.
R exchange files live in temporary directories, not under `tables/`.

## Tables

- `tables/enrichment_scores.csv`: `Cell` plus one score column per matched gene set.
- `tables/gene_set_overlap.csv`: requested and matched gene counts, chosen feature-label source and example matched identifiers.
- `tables/top_pathways.csv`: `gene_set`, `mean_score`, `mean_abs_score`, ranked by absolute mean then name.
- `tables/group_mean_scores.csv`: group-by-pathway means, only with a valid grouping column.
- `tables/group_high_fraction.csv`: per-group fractions above each pathway's overall median, only with a valid grouping column.

`processed.h5ad` contains `enrich__...` obs columns and the
`uns["sc_pathway_scoring"]` label map. R's `aucell_scores.csv` and its
expression TSV are temporary. `top_pathway_scores_long.csv`,
`gene_expression.csv` and cell metadata are plot source data, not additional
analysis tables. R-enhanced figures require `--r-enhanced`.

## Diagnostics

`run_info(scores)` reports method, seed, expression source, feature-label
source and skipped sets. CLI `result.json["summary"]` reports the method,
requested/scored set counts and those sources. The synthetic CLI gene sets
have no biological meaning; the step example uses PBMC lineage genes.
