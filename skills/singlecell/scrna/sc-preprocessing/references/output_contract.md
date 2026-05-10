## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── info.json
├── input.h5ad
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── X_norm.csv
│   ├── cell_metadata.csv
│   ├── cluster_summary.csv
│   ├── embedding_points.csv
│   ├── gene_expression.csv
│   ├── hvg.csv
│   ├── hvg_summary.csv
│   ├── obs.csv
│   ├── pca.csv
│   ├── pca_embedding.csv
│   ├── pca_variance_ratio.csv
│   ├── preprocess_summary.csv
│   └── qc_metrics_per_cell.csv
└── figures/
    ├── highly_variable_genes.png
    ├── pca_variance.png
    ├── qc_violin.png
    └── r_hvg_violin.png
```

## File contents

- `tables/X_norm.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/cluster_summary.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/embedding_points.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/gene_expression.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/hvg.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/hvg_summary.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/obs.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/pca.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/pca_embedding.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/pca_variance_ratio.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/preprocess_summary.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `tables/qc_metrics_per_cell.csv` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `figures/highly_variable_genes.png` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `figures/pca_variance.png` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `figures/qc_violin.png` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `figures/r_hvg_violin.png` — written by `sc_preprocess.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_preprocess.py`.
- `commands.sh` — written by `sc_preprocess.py`.
- `info.json` — written by `sc_preprocess.py`.
- `input.h5ad` — written by `sc_preprocess.py`.
- `manifest.json` — written by `sc_preprocess.py`.
- `processed.h5ad` — written by `sc_preprocess.py`.
- `requirements.txt` — written by `sc_preprocess.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_preprocess.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
