## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── aucell_scores.csv
│   ├── cell_metadata.csv
│   ├── enrichment_scores.csv
│   ├── expression_matrix.tsv
│   ├── gene_expression.csv
│   ├── gene_set_overlap.csv
│   ├── group_high_fraction.csv
│   ├── group_mean_scores.csv
│   ├── top_pathway_scores_long.csv
│   └── top_pathways.csv
└── figures/
    └── r_pathway_violin.png
```

## File contents

- `tables/aucell_scores.csv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `tables/enrichment_scores.csv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `tables/expression_matrix.tsv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `tables/gene_expression.csv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `tables/gene_set_overlap.csv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `tables/group_high_fraction.csv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `tables/group_mean_scores.csv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `tables/top_pathway_scores_long.csv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `tables/top_pathways.csv` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `figures/r_pathway_violin.png` — written by `sc_pathway_scoring.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_pathway_scoring.py`.
- `commands.sh` — written by `sc_pathway_scoring.py`.
- `manifest.json` — written by `sc_pathway_scoring.py`.
- `processed.h5ad` — written by `sc_pathway_scoring.py`.
- `requirements.txt` — written by `sc_pathway_scoring.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_pathway_scoring.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
