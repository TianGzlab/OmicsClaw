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
│   ├── cellrank_driver_genes.csv
│   ├── palantir_branch_probs.csv
│   ├── trajectory_cluster_summary.csv
│   ├── trajectory_diffmap_points.csv
│   ├── trajectory_driver_genes.csv
│   ├── trajectory_fate_probabilities.csv
│   ├── trajectory_fate_probabilities_wide.csv
│   ├── trajectory_genes.csv
│   ├── trajectory_run_summary.csv
│   ├── trajectory_spatial_points.csv
│   ├── trajectory_summary.csv
│   ├── trajectory_terminal_states.csv
│   └── trajectory_umap_points.csv
└── figures/
    ├── cellrank_fate_circular.png
    ├── cellrank_fate_heatmap.png
    ├── cellrank_fate_map.png
    ├── cellrank_gene_trends.png
    ├── trajectory_cluster_summary.png
    ├── trajectory_diffmap.png
    ├── trajectory_entropy_distribution.png
    ├── trajectory_fate_probability_distribution.png
    ├── trajectory_genes_barplot.png
    ├── trajectory_pseudotime_distribution.png
    ├── trajectory_pseudotime_embedding.png
    └── trajectory_pseudotime_spatial.png
```

## File contents

- `tables/cellrank_driver_genes.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/palantir_branch_probs.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_cluster_summary.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_diffmap_points.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_driver_genes.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_fate_probabilities.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_fate_probabilities_wide.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_genes.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_run_summary.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_spatial_points.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_summary.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_terminal_states.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `tables/trajectory_umap_points.csv` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/cellrank_fate_circular.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/cellrank_fate_heatmap.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/cellrank_fate_map.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/cellrank_gene_trends.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/trajectory_cluster_summary.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/trajectory_diffmap.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/trajectory_entropy_distribution.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/trajectory_fate_probability_distribution.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/trajectory_genes_barplot.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/trajectory_pseudotime_distribution.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/trajectory_pseudotime_embedding.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `figures/trajectory_pseudotime_spatial.png` — written by `spatial_trajectory.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_trajectory.py`.
- `environment.txt` — written by `spatial_trajectory.py`.
- `manifest.json` — written by `spatial_trajectory.py`.
- `processed.h5ad` — written by `spatial_trajectory.py`.
- `r_visualization.sh` — written by `spatial_trajectory.py`.
- `requirements.txt` — written by `spatial_trajectory.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_trajectory.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
