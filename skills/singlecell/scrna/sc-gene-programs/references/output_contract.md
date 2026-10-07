# Outputs

The Python API returns in-memory objects and figures. It does not create a
report directory. Examples persist selected objects with `write_output`.

The standalone CLI writes `processed.h5ad`, `report.md` and `result.json`.
Its plots are under `figures/`; plot source tables are under `figure_data/`.
R exchange files live in temporary directories, not under `tables/`.

## Tables

- `tables/program_usage.csv`: cell IDs by program names.
- `tables/program_weights.csv`: program names by gene IDs.
- `tables/top_program_genes.csv`: `program`, `rank`, `gene`, `weight`.
- `tables/program_tpm.csv`: cNMF TPM spectra, only when supplied by cNMF.

The CLI adds `obsm["X_gene_programs"]` and `uns["gene_programs"]` to the
saved AnnData. The API also retains weight and top-gene tables and a JSON
run record in uns. Use `program_weights`, `top_program_genes` and
`run_info` to read them.

`figures/mean_program_usage.png` is produced for nonempty usage.
`figures/program_correlation.png` needs multiple programs.
`figure_data/program_correlation.csv` is the corresponding source table,
not a file under `tables/`. Optional R-enhanced figures go under
`figures/r_enhanced/`.

## Diagnostics

`run_info` names requested/executed methods and any missing-cNMF fallback.
CLI `result.json["summary"]` includes backend, effective program count,
reconstruction error and degenerate-output diagnostics. Degenerate results
are reported without forcing a nonzero exit.
