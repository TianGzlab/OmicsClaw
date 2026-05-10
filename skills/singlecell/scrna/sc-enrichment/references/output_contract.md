## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── background_genes.txt
├── commands.sh
├── manifest.json
├── processed.h5ad
├── r_plot_metadata.json
├── requirements.txt
├── tables/
│   ├── cell_metadata.csv
│   ├── clusterprofiler_results.csv
│   ├── de_for_gsea_r.csv
│   ├── de_full.csv
│   ├── enrichment_results.csv
│   ├── enrichment_significant.csv
│   ├── group_expr_for_gsva.csv
│   ├── group_summary.csv
│   ├── gsea_input.csv
│   ├── gsea_r_results.csv
│   ├── gsea_running_scores.csv
│   ├── gsva_r_scores.csv
│   ├── markers_all.csv
│   ├── ora_input.csv
│   ├── ranking_input.csv
│   └── top_terms.csv
└── figures/
    ├── gsva_r_heatmap.png
    ├── r_enrichment_bar.png
    ├── r_enrichment_dotplot.png
    ├── r_enrichment_enrichmap.png
    ├── r_enrichment_lollipop.png
    ├── r_enrichment_network.png
    ├── r_gsea_mountain.png
    └── r_gsea_nes_heatmap.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/clusterprofiler_results.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/de_for_gsea_r.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/de_full.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/enrichment_results.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/enrichment_significant.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/group_expr_for_gsva.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/group_summary.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/gsea_input.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/gsea_r_results.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/gsea_running_scores.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/gsva_r_scores.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/markers_all.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/ora_input.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/ranking_input.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `tables/top_terms.csv` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `figures/gsva_r_heatmap.png` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `figures/r_enrichment_bar.png` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `figures/r_enrichment_dotplot.png` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `figures/r_enrichment_enrichmap.png` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `figures/r_enrichment_lollipop.png` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `figures/r_enrichment_network.png` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `figures/r_gsea_mountain.png` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `figures/r_gsea_nes_heatmap.png` — written by `sc_enrichment.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_enrichment.py`.
- `background_genes.txt` — written by `sc_enrichment.py`.
- `commands.sh` — written by `sc_enrichment.py`.
- `manifest.json` — written by `sc_enrichment.py`.
- `processed.h5ad` — written by `sc_enrichment.py`.
- `r_plot_metadata.json` — written by `sc_enrichment.py`.
- `requirements.txt` — written by `sc_enrichment.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_enrichment.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
