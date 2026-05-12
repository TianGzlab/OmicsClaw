## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── manifest.json
├── processed.h5ad
├── tables/
│   ├── cell_metadata.csv
│   ├── cluster_qc_summary.csv
│   ├── cluster_summary.csv
│   ├── clustering_summary.csv
│   └── embedding_points.csv
└── figures/
    ├── auto_resolution_search.png
    ├── cluster_qc_heatmap.png
    ├── cluster_size_summary.png
    ├── embedding_clusters.png
    ├── embedding_comparison.png
    ├── pca_scatter.png
    ├── pca_variance.png
    ├── r_cell_barplot.png
    ├── r_cell_proportion.png
    ├── r_embedding_discrete.png
    └── r_embedding_feature.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `tables/cluster_qc_summary.csv` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `tables/cluster_summary.csv` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `tables/clustering_summary.csv` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `tables/embedding_points.csv` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/auto_resolution_search.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/cluster_qc_heatmap.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/cluster_size_summary.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/embedding_clusters.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/embedding_comparison.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/pca_scatter.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/pca_variance.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/r_cell_barplot.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/r_cell_proportion.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_discrete.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_feature.png` — written by `sc_cluster.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_cluster.py`.
- `commands.sh` — written by `sc_cluster.py`.
- `manifest.json` — written by `sc_cluster.py`.
- `processed.h5ad` — written by `sc_cluster.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_cluster.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
