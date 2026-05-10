## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── fastccc_input.h5ad
├── input.h5ad
├── manifest.json
├── processed.h5ad
├── r_visualization.sh
├── requirements.txt
├── tables/
│   ├── cellchat_centrality.csv
│   ├── cellchat_count_matrix.csv
│   ├── cellchat_pathways.csv
│   ├── cellchat_results.csv
│   ├── cellchat_weight_matrix.csv
│   ├── communication_run_summary.csv
│   ├── communication_spatial_points.csv
│   ├── communication_summary.csv
│   ├── communication_umap_points.csv
│   ├── complex_composition_table.csv
│   ├── complex_table.csv
│   ├── gene_table.csv
│   ├── interaction_table.csv
│   ├── lr_interactions.csv
│   ├── meta.tsv
│   ├── protein_table.csv
│   ├── signaling_roles.csv
│   ├── source_target_summary.csv
│   └── top_interactions.csv
└── figures/
    ├── communication_pvalue_distribution.png
    ├── communication_roles_spatial.png
    ├── communication_score_vs_significance.png
    ├── lr_dotplot.png
    ├── lr_heatmap.png
    ├── lr_spatial.png
    ├── signaling_roles.png
    └── source_target_summary.png
```

## File contents

- `tables/cellchat_centrality.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/cellchat_count_matrix.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/cellchat_pathways.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/cellchat_results.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/cellchat_weight_matrix.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/communication_run_summary.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/communication_spatial_points.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/communication_summary.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/communication_umap_points.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/complex_composition_table.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/complex_table.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/gene_table.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/interaction_table.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/lr_interactions.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/meta.tsv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/protein_table.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/signaling_roles.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/source_target_summary.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `tables/top_interactions.csv` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `figures/communication_pvalue_distribution.png` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `figures/communication_roles_spatial.png` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `figures/communication_score_vs_significance.png` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `figures/lr_dotplot.png` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `figures/lr_heatmap.png` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `figures/lr_spatial.png` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `figures/signaling_roles.png` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `figures/source_target_summary.png` — written by `spatial_communication.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_communication.py`.
- `fastccc_input.h5ad` — written by `spatial_communication.py`.
- `input.h5ad` — written by `spatial_communication.py`.
- `manifest.json` — written by `spatial_communication.py`.
- `processed.h5ad` — written by `spatial_communication.py`.
- `r_visualization.sh` — written by `spatial_communication.py`.
- `requirements.txt` — written by `spatial_communication.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_communication.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
