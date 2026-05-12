## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   ├── hub_genes.csv
│   ├── interaction_edges.csv
│   └── node_centrality.csv
└── figures/
    ├── hub_genes_barplot.png
    └── ppi_network.png
```

## File contents

- `tables/hub_genes.csv` — written by `bulkrna_ppi_network.py` (or its imported `_lib/` helpers).
- `tables/interaction_edges.csv` — written by `bulkrna_ppi_network.py` (or its imported `_lib/` helpers).
- `tables/node_centrality.csv` — written by `bulkrna_ppi_network.py` (or its imported `_lib/` helpers).
- `figures/hub_genes_barplot.png` — written by `bulkrna_ppi_network.py` (or its imported `_lib/` helpers).
- `figures/ppi_network.png` — written by `bulkrna_ppi_network.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_ppi_network.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_bulkrna_ppi_genes.csv` — generated only on `--demo`.

## Notes

Auto-generated from `bulkrna_ppi_network.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
