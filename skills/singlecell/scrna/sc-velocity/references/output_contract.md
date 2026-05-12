## Output Structure

```
output_directory/
├── report.md
├── result.json
├── adata_with_velocity.h5ad
├── analysis_summary.txt
├── commands.sh
├── manifest.json
├── processed.h5ad
├── tables/
│   ├── cell_metadata.csv
│   ├── top_velocity_genes.csv
│   ├── velocity_cells.csv
│   └── velocity_summary.csv
└── figures/
    ├── latent_time_distribution.png
    ├── latent_time_umap.png
    ├── r_embedding_discrete.png
    ├── r_embedding_feature.png
    ├── r_velocity.png
    ├── velocity_magnitude_distribution.png
    ├── velocity_magnitude_umap.png
    ├── velocity_stream.png
    └── velocity_top_genes.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `tables/top_velocity_genes.csv` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_cells.csv` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_summary.csv` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `figures/latent_time_distribution.png` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `figures/latent_time_umap.png` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_discrete.png` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_feature.png` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `figures/r_velocity.png` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_magnitude_distribution.png` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_magnitude_umap.png` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_stream.png` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_top_genes.png` — written by `sc_velocity.py` (or its imported `_lib/` helpers).
- `adata_with_velocity.h5ad` — written by `sc_velocity.py`.
- `analysis_summary.txt` — written by `sc_velocity.py`.
- `commands.sh` — written by `sc_velocity.py`.
- `manifest.json` — written by `sc_velocity.py`.
- `processed.h5ad` — written by `sc_velocity.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_velocity.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
