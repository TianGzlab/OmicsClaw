## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── wgcna_info.json
├── tables/
│   ├── counts.csv
│   ├── gene_modules.csv
│   ├── hub_genes.csv
│   ├── module_assignments.csv
│   ├── soft_power_table.csv
│   └── threshold_fit.csv
└── figures/
    ├── module_dendrogram.png
    ├── module_sizes.png
    └── scale_free_fit.png
```

## File contents

- `tables/counts.csv` — written by `bulkrna_coexpression.py` (or its imported `_lib/` helpers).
- `tables/gene_modules.csv` — written by `bulkrna_coexpression.py` (or its imported `_lib/` helpers).
- `tables/hub_genes.csv` — written by `bulkrna_coexpression.py` (or its imported `_lib/` helpers).
- `tables/module_assignments.csv` — written by `bulkrna_coexpression.py` (or its imported `_lib/` helpers).
- `tables/soft_power_table.csv` — written by `bulkrna_coexpression.py` (or its imported `_lib/` helpers).
- `tables/threshold_fit.csv` — written by `bulkrna_coexpression.py` (or its imported `_lib/` helpers).
- `figures/module_dendrogram.png` — written by `bulkrna_coexpression.py` (or its imported `_lib/` helpers).
- `figures/module_sizes.png` — written by `bulkrna_coexpression.py` (or its imported `_lib/` helpers).
- `figures/scale_free_fit.png` — written by `bulkrna_coexpression.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_coexpression.py`.
- `wgcna_info.json` — written by `bulkrna_coexpression.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_bulkrna_counts.csv` — generated only on `--demo`.

## Notes

Auto-generated from `bulkrna_coexpression.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
