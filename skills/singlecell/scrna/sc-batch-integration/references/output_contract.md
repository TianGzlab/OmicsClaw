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
│   ├── batch_mixing_matrix.csv
│   ├── batch_sizes.csv
│   ├── cell_metadata.csv
│   ├── cluster_sizes.csv
│   ├── embedding.csv
│   ├── integration_metrics.csv
│   ├── integration_summary.csv
│   ├── obs.csv
│   ├── umap.csv
│   └── umap_points.csv
└── figures/
    ├── batch_mixing_heatmap.png
    ├── integration_metrics.png
    └── r_embedding_discrete.png
```

## File contents

- `tables/batch_mixing_matrix.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `tables/batch_sizes.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `tables/cluster_sizes.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `tables/embedding.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `tables/integration_metrics.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `tables/integration_summary.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `tables/obs.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `tables/umap.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `tables/umap_points.csv` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `figures/batch_mixing_heatmap.png` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `figures/integration_metrics.png` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_discrete.png` — written by `sc_integrate.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_integrate.py`.
- `commands.sh` — written by `sc_integrate.py`.
- `input.h5ad` — written by `sc_integrate.py`.
- `manifest.json` — written by `sc_integrate.py`.
- `processed.h5ad` — written by `sc_integrate.py`.
- `requirements.txt` — written by `sc_integrate.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_integrate.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
