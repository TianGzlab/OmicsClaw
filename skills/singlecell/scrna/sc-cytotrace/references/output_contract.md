## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── processed.h5ad
├── tables/
│   ├── cell_metadata.csv
│   ├── cytotrace_embedding.csv
│   └── cytotrace_scores.csv
└── figures/
    ├── potency_composition.png
    ├── potency_umap.png
    ├── r_cell_density.png
    ├── r_cytotrace_boxplot.png
    ├── r_embedding_discrete.png
    ├── r_embedding_feature.png
    └── score_distribution.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `tables/cytotrace_embedding.csv` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `tables/cytotrace_scores.csv` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `figures/potency_composition.png` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `figures/potency_umap.png` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `figures/r_cell_density.png` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `figures/r_cytotrace_boxplot.png` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_discrete.png` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_feature.png` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `figures/score_distribution.png` — written by `sc_cytotrace.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_cytotrace.py`.
- `commands.sh` — written by `sc_cytotrace.py`.
- `processed.h5ad` — written by `sc_cytotrace.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_cytotrace.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
