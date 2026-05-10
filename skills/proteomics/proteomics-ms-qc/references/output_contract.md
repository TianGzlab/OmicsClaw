## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
└── tables/
    └── qc_metrics.csv
```

## File contents

- `tables/qc_metrics.csv` — written by `proteomics_ms_qc.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `proteomics_ms_qc.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_proteomics.csv` — generated only on `--demo`.

## Notes

Auto-generated from `proteomics_ms_qc.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
