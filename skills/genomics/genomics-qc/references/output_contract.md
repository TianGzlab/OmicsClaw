## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
└── tables/
    ├── per_base_quality.csv
    ├── qc_metrics.csv
    └── read_length_distribution.csv
```

## File contents

- `tables/per_base_quality.csv` — written by `genomics_qc.py` (or its imported `_lib/` helpers).
- `tables/qc_metrics.csv` — written by `genomics_qc.py` (or its imported `_lib/` helpers).
- `tables/read_length_distribution.csv` — written by `genomics_qc.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `genomics_qc.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `genomics_qc.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
