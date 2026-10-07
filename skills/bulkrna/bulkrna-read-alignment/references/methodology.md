# Methodology

`summarize` defaults to STAR, matching the CLI. Choose `hisat2` or `salmon`
explicitly; filenames do not override that choice. STAR/HISAT2 include unique
and multimapped counts. Salmon meta_info reports total mapped counts only.

- `summarize` rejects absent or inconsistent read counts.
- `run_info` states that logs provide neither gene-body coverage nor inferred strandedness.
- `coverage_figure` needs an explicit measured profile. `demo_coverage` is synthetic and is only used by `--demo`.
- `mapped_rate` for Salmon does not mean uniquely mapped rate.
- HISAT2 `unmapped` is the residual after concordant pairs and includes discordant/unpaired mappings; `run_info` records this limitation.
