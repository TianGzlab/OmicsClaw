## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── alignment_stats.csv
```

## File contents

- `tables/alignment_stats.csv` — written by `genomics_alignment.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_alignment.sam` — generated only on `--demo`.

## Notes

Auto-generated from `genomics_alignment.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
