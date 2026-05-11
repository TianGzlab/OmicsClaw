## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── input.h5ad
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── counts.csv
│   ├── de_full.csv
│   ├── de_group_summary.csv
│   ├── de_top_markers.csv
│   ├── deseq2_results.csv
│   ├── gene_expression.csv
│   ├── markers_top.csv
│   ├── mast_results.csv
│   ├── metadata.csv
│   └── pseudobulk_summary.csv
└── figures/
    ├── marker_dotplot.png
    ├── pseudobulk_group_summary.png
    ├── r_de_heatmap.png
    ├── r_de_manhattan.png
    ├── r_de_volcano.png
    ├── r_feature_cor.png
    ├── r_feature_violin.png
    └── rank_genes_groups.png
```

## File contents

- `tables/counts.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `tables/de_full.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `tables/de_group_summary.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `tables/de_top_markers.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `tables/deseq2_results.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `tables/gene_expression.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `tables/markers_top.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `tables/mast_results.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `tables/metadata.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `tables/pseudobulk_summary.csv` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `figures/marker_dotplot.png` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `figures/pseudobulk_group_summary.png` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `figures/r_de_heatmap.png` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `figures/r_de_manhattan.png` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `figures/r_de_volcano.png` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `figures/r_feature_cor.png` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `figures/r_feature_violin.png` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `figures/rank_genes_groups.png` — written by `sc_de.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `sc_de.py`.
- `input.h5ad` — written by `sc_de.py`.
- `manifest.json` — written by `sc_de.py`.
- `processed.h5ad` — written by `sc_de.py`.
- `requirements.txt` — written by `sc_de.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_de.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
