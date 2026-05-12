## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── processed.h5ad
├── requirements.txt
└── tables/
    └── cell_metadata.csv
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_standardize_input.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_standardize_input.py`.
- `commands.sh` — written by `sc_standardize_input.py`.
- `processed.h5ad` — written by `sc_standardize_input.py`.
- `requirements.txt` — written by `sc_standardize_input.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_standardize_input.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
