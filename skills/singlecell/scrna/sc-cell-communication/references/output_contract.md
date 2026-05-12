## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── input.h5ad
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── _matrix.csv
│   ├── cellchat_centrality.csv
│   ├── cellchat_count_matrix.csv
│   ├── cellchat_pathways.csv
│   ├── cellchat_results.csv
│   ├── cellchat_weight_matrix.csv
│   ├── cellphonedb_means.csv
│   ├── cellphonedb_pvalues.csv
│   ├── cellphonedb_significant_means.csv
│   ├── group_role_summary.csv
│   ├── lr_interactions.csv
│   ├── meta.tsv
│   ├── nichenet_ligand_activities.csv
│   ├── nichenet_ligand_receptors.csv
│   ├── nichenet_ligand_target_links.csv
│   ├── nichenet_lr_network.csv
│   ├── pathway_summary.csv
│   ├── sender_receiver_summary.csv
│   └── top_interactions.csv
└── figures/
    ├── r_ccc_bipartite.png
    ├── r_ccc_bubble.png
    ├── r_ccc_diff_network.png
    ├── r_ccc_heatmap.png
    ├── r_ccc_network.png
    ├── r_ccc_stat_bar.png
    ├── r_ccc_stat_scatter.png
    └── r_ccc_stat_violin.png
```

## File contents

- `tables/_matrix.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/cellchat_centrality.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/cellchat_count_matrix.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/cellchat_pathways.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/cellchat_results.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/cellchat_weight_matrix.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/cellphonedb_means.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/cellphonedb_pvalues.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/cellphonedb_significant_means.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/group_role_summary.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/lr_interactions.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/meta.tsv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/nichenet_ligand_activities.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/nichenet_ligand_receptors.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/nichenet_ligand_target_links.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/nichenet_lr_network.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/pathway_summary.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/sender_receiver_summary.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `tables/top_interactions.csv` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `figures/r_ccc_bipartite.png` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `figures/r_ccc_bubble.png` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `figures/r_ccc_diff_network.png` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `figures/r_ccc_heatmap.png` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `figures/r_ccc_network.png` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `figures/r_ccc_stat_bar.png` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `figures/r_ccc_stat_scatter.png` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `figures/r_ccc_stat_violin.png` — written by `sc_cell_communication.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `sc_cell_communication.py`.
- `input.h5ad` — written by `sc_cell_communication.py`.
- `manifest.json` — written by `sc_cell_communication.py`.
- `processed.h5ad` — written by `sc_cell_communication.py`.
- `requirements.txt` — written by `sc_cell_communication.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_cell_communication.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
