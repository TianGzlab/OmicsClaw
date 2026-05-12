## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
└── tables/
    ├── differential_abundance.csv
    └── significant.csv
```

## File contents

- `tables/differential_abundance.csv` — written by `proteomics_de.py` (or its imported `_lib/` helpers).
- `tables/significant.csv` — written by `proteomics_de.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `proteomics_de.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `proteomics_de.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
