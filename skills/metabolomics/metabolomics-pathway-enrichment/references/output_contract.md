# Output contract

`tables/pathway_enrichment.csv`, `report.md` and `result.json`. Demo mode also writes its synthetic input CSV at the output root.

The function library returns tables and Figures without file writes.
`run_info` reads DataFrame diagnostics; `keep=False` removes them.

`enrich` implements only ora and rejects fella/mummichog. Default reference_scope is demo; supply pathways= for real local reference data. `tables/pathway_enrichment.csv` has a stable schema even with no overlap.
