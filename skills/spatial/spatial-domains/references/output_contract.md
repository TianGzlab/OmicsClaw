## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── manifest.json
├── processed.h5ad
├── r_visualization.sh
├── requirements.txt
├── tables/
│   ├── domain_assignments.csv
│   ├── domain_counts.csv
│   ├── domain_method_embedding_points.csv
│   ├── domain_neighbor_mixing.csv
│   ├── domain_spatial_points.csv
│   ├── domain_summary.csv
│   └── domain_umap_points.csv
└── figures/
    ├── domain_local_purity_histogram.png
    ├── domain_local_purity_spatial.png
    ├── domain_neighbor_mixing.png
    ├── domain_sizes.png
    ├── pca_domains.png
    ├── spatial_domains.png
    └── umap_domains.png
```

## File contents

- `tables/domain_assignments.csv` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `tables/domain_counts.csv` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `tables/domain_method_embedding_points.csv` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `tables/domain_neighbor_mixing.csv` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `tables/domain_spatial_points.csv` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `tables/domain_summary.csv` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `tables/domain_umap_points.csv` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `figures/domain_local_purity_histogram.png` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `figures/domain_local_purity_spatial.png` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `figures/domain_neighbor_mixing.png` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `figures/domain_sizes.png` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `figures/pca_domains.png` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `figures/spatial_domains.png` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `figures/umap_domains.png` — written by `spatial_domains.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_domains.py`.
- `manifest.json` — written by `spatial_domains.py`.
- `processed.h5ad` — written by `spatial_domains.py`.
- `r_visualization.sh` — written by `spatial_domains.py`.
- `requirements.txt` — written by `spatial_domains.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_visium.h5ad` — generated only on `--demo`.

## Notes

Auto-generated from `spatial_domains.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
