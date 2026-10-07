# Output contract

The function library writes no files. `cytotrace` annotates the supplied
AnnData with `cytotrace_score`, `cytotrace_potency` and `cytotrace_gene_count`
columns; table and figure functions return objects for the step to save.
These names retain compatibility with the CLI: the method is a gene-count
proxy with neighbor smoothing, not the CytoTRACE2 pretrained model.

The CLI writes `processed.h5ad`, `tables/cytotrace_scores.csv`,
`report.md` and `result.json`. Plot-source data live in
`figure_data/cytotrace_embedding.csv`; embedding plots require a usable
embedding. R-enhanced figures are optional and appear only when requested
and successfully rendered. Six potency bins are relative categories, not
validated developmental labels.
