## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── input.h5ad
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── cell_metadata.csv
│   ├── doublet_calls.csv
│   ├── doublet_summary.csv
│   ├── doubletfinder_results.csv
│   ├── embedding_points.csv
│   ├── group_summary.csv
│   ├── scdblfinder_results.csv
│   ├── scds_results.csv
│   └── summary.csv
└── figures/
    ├── embedding_doublet_calls.png
    ├── embedding_doublet_scores.png
    ├── embedding_doublet_vs_group.png
    ├── r_embedding_discrete.png
    ├── r_embedding_feature.png
    └── r_feature_violin.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `tables/doublet_calls.csv` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `tables/doublet_summary.csv` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `tables/doubletfinder_results.csv` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `tables/embedding_points.csv` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `tables/group_summary.csv` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `tables/scdblfinder_results.csv` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `tables/scds_results.csv` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `tables/summary.csv` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `figures/embedding_doublet_calls.png` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `figures/embedding_doublet_scores.png` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `figures/embedding_doublet_vs_group.png` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_discrete.png` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_feature.png` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `figures/r_feature_violin.png` — written by `sc_doublet.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_doublet.py`.
- `commands.sh` — written by `sc_doublet.py`.
- `input.h5ad` — written by `sc_doublet.py`.
- `manifest.json` — written by `sc_doublet.py`.
- `processed.h5ad` — written by `sc_doublet.py`.
- `requirements.txt` — written by `sc_doublet.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_doublet.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
