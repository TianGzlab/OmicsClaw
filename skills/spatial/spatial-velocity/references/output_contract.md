## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── environment.txt
├── manifest.json
├── processed.h5ad
├── r_visualization.sh
├── requirements.txt
├── tables/
│   ├── cell_velocity_metrics.csv
│   ├── gene_velocity_summary.csv
│   ├── top_velocity_cells.csv
│   ├── top_velocity_genes.csv
│   ├── velocity_cell_metrics.csv
│   ├── velocity_cluster_summary.csv
│   ├── velocity_gene_hits.csv
│   ├── velocity_gene_summary.csv
│   ├── velocity_run_summary.csv
│   ├── velocity_spatial_points.csv
│   ├── velocity_summary.csv
│   ├── velocity_top_cells.csv
│   ├── velocity_top_genes.csv
│   └── velocity_umap_points.csv
└── figures/
    ├── velocity_cluster_summary.png
    ├── velocity_confidence_distribution.png
    ├── velocity_confidence_spatial.png
    ├── velocity_confidence_umap.png
    ├── velocity_heatmap.png
    ├── velocity_latent_time_spatial.png
    ├── velocity_layer_proportions.png
    ├── velocity_paga.png
    ├── velocity_phase.png
    ├── velocity_pseudotime_spatial.png
    ├── velocity_speed_distribution.png
    ├── velocity_speed_spatial.png
    ├── velocity_speed_umap.png
    ├── velocity_stream_spatial.png
    ├── velocity_stream_umap.png
    ├── velocity_top_genes_barplot.png
    └── velocity_transition_confidence_umap.png
```

## File contents

- `tables/cell_velocity_metrics.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/gene_velocity_summary.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/top_velocity_cells.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/top_velocity_genes.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_cell_metrics.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_cluster_summary.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_gene_hits.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_gene_summary.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_run_summary.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_spatial_points.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_summary.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_top_cells.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_top_genes.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `tables/velocity_umap_points.csv` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_cluster_summary.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_confidence_distribution.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_confidence_spatial.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_confidence_umap.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_heatmap.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_latent_time_spatial.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_layer_proportions.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_paga.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_phase.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_pseudotime_spatial.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_speed_distribution.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_speed_spatial.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_speed_umap.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_stream_spatial.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_stream_umap.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_top_genes_barplot.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `figures/velocity_transition_confidence_umap.png` — written by `spatial_velocity.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_velocity.py`.
- `environment.txt` — written by `spatial_velocity.py`.
- `manifest.json` — written by `spatial_velocity.py`.
- `processed.h5ad` — written by `spatial_velocity.py`.
- `r_visualization.sh` — written by `spatial_velocity.py`.
- `requirements.txt` — written by `spatial_velocity.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_velocity.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
