## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── pathway_enrichment.csv
```

## File contents

- `tables/pathway_enrichment.csv` — per-pathway over-representation result with columns `pathway`, `n_pathway_members`, `n_query_in_pathway`, `pvalue`, `fdr` (BH-adjusted). Written at `met_pathway.py:314`.
- `report.md` — run parameters (`--method`) plus per-pathway summary.
- `result.json` — `summary` includes `n_metabolites`, `n_pathways_tested` (= 9 for the embedded `DEMO_METABOLIC_PATHWAYS`), `n_significant`, `method` (recorded; only ORA actually runs).

## Notes

- No `figures/` directory.
- The pathway database is the hard-coded 9-pathway `DEMO_METABOLIC_PATHWAYS` dict at `met_pathway.py:45`.
- `--method mummichog` and `--method fella` are recorded but produce ORA results regardless.
