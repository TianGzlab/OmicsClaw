## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── auc_matrix.csv
│   ├── cell_metadata.csv
│   ├── gene_expression.csv
│   ├── regulon_summary.csv
│   └── top_adjacencies.csv
└── figures/
    ├── r_regulon_cor.png
    └── r_regulon_violin.png
```

## File contents

- `tables/auc_matrix.csv` — written by `sc_grn.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_grn.py` (or its imported `_lib/` helpers).
- `tables/gene_expression.csv` — written by `sc_grn.py` (or its imported `_lib/` helpers).
- `tables/regulon_summary.csv` — written by `sc_grn.py` (or its imported `_lib/` helpers).
- `tables/top_adjacencies.csv` — written by `sc_grn.py` (or its imported `_lib/` helpers).
- `figures/r_regulon_cor.png` — written by `sc_grn.py` (or its imported `_lib/` helpers).
- `figures/r_regulon_violin.png` — written by `sc_grn.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_grn.py`.
- `commands.sh` — written by `sc_grn.py`.
- `manifest.json` — written by `sc_grn.py`.
- `processed.h5ad` — written by `sc_grn.py`.
- `requirements.txt` — written by `sc_grn.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_tf_list.txt` — generated only on `--demo`.

## Notes

Auto-generated from `sc_grn.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
