## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
└── tables/
    └── peptides.csv
```

## File contents

- `tables/peptides.csv` — written by `proteomics_identification.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `proteomics_identification.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `proteomics_identification.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
