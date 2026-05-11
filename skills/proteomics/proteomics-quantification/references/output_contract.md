## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
└── tables/
    └── protein_abundance.csv
```

## File contents

- `tables/protein_abundance.csv` — written by `proteomics_quantification.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `proteomics_quantification.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `proteomics_quantification.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
