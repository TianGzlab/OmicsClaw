## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   ├── cpm_normalized.csv
│   └── sample_stats.csv
└── figures/
    ├── expression_density.png
    ├── gene_detection.png
    ├── library_sizes.png
    └── sample_correlation.png
```

## File contents

- `tables/cpm_normalized.csv` — written by `bulkrna_qc.py` (or its imported `_lib/` helpers).
- `tables/sample_stats.csv` — written by `bulkrna_qc.py` (or its imported `_lib/` helpers).
- `figures/expression_density.png` — written by `bulkrna_qc.py` (or its imported `_lib/` helpers).
- `figures/gene_detection.png` — written by `bulkrna_qc.py` (or its imported `_lib/` helpers).
- `figures/library_sizes.png` — written by `bulkrna_qc.py` (or its imported `_lib/` helpers).
- `figures/sample_correlation.png` — written by `bulkrna_qc.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_qc.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_bulkrna_counts.csv` — generated only on `--demo`.

## Notes

Auto-generated from `bulkrna_qc.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
