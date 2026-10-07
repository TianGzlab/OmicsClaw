# Output contract

`tables/pathway_enrichment.csv`, `report.md` and `result.json`. Demo mode also writes its synthetic input CSV at the output root.

The function library returns tables and Figures without file writes.
`run_info` reads DataFrame diagnostics; `keep=False` removes them.

`enrich` requires explicit `pathways=` and implements only ora. `result.json` preserves `data.run_info.reference_scope` as demo or provided. `tables/pathway_enrichment.csv` has a stable schema even with no overlap.
