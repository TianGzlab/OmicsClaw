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
│   ├── fate_probabilities.csv
│   ├── gene_expression.csv
│   ├── monocle3_pseudotime.csv
│   ├── monocle3_trajectory.csv
│   ├── pseudotime_cells.csv
│   ├── pseudotime_points.csv
│   ├── slingshot_branches.csv
│   ├── slingshot_curves.csv
│   ├── slingshot_pseudotime.csv
│   ├── trajectory_genes.csv
│   └── trajectory_summary.csv
└── figures/
    ├── monocle3_trajectory_graph.png
    ├── r_cell_density.png
    ├── r_embedding_discrete.png
    ├── r_embedding_feature.png
    ├── r_pseudotime_dynamic.png
    ├── r_pseudotime_heatmap.png
    └── r_pseudotime_lineage.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/fate_probabilities.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/gene_expression.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/monocle3_pseudotime.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/monocle3_trajectory.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/pseudotime_cells.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/pseudotime_points.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/slingshot_branches.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/slingshot_curves.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/slingshot_pseudotime.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/trajectory_genes.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `tables/trajectory_summary.csv` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `figures/monocle3_trajectory_graph.png` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `figures/r_cell_density.png` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_discrete.png` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_feature.png` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `figures/r_pseudotime_dynamic.png` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `figures/r_pseudotime_heatmap.png` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `figures/r_pseudotime_lineage.png` — written by `sc_pseudotime.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_pseudotime.py`.
- `commands.sh` — written by `sc_pseudotime.py`.
- `input.h5ad` — written by `sc_pseudotime.py`.
- `manifest.json` — written by `sc_pseudotime.py`.
- `processed.h5ad` — written by `sc_pseudotime.py`.
- `requirements.txt` — written by `sc_pseudotime.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_pseudotime.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
