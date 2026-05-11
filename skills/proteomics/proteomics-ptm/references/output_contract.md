## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    ├── ptm_class_I_sites.csv
    └── ptm_sites.csv
```

## File contents

- `tables/ptm_class_I_sites.csv` — written by `proteomics_ptm.py` (or its imported `_lib/` helpers).
- `tables/ptm_sites.csv` — written by `proteomics_ptm.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_ptm_sites.csv` — generated only on `--demo`.

## Notes

Auto-generated from `proteomics_ptm.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
