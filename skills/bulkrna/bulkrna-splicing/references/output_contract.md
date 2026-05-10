## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   ├── significant_events.csv
│   └── splicing_events.csv
└── figures/
    ├── dpsi_distribution.png
    ├── event_type_distribution.png
    └── volcano_splicing.png
```

## File contents

- `tables/significant_events.csv` — written by `bulkrna_splicing.py` (or its imported `_lib/` helpers).
- `tables/splicing_events.csv` — written by `bulkrna_splicing.py` (or its imported `_lib/` helpers).
- `figures/dpsi_distribution.png` — written by `bulkrna_splicing.py` (or its imported `_lib/` helpers).
- `figures/event_type_distribution.png` — written by `bulkrna_splicing.py` (or its imported `_lib/` helpers).
- `figures/volcano_splicing.png` — written by `bulkrna_splicing.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_splicing.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `bulkrna_splicing.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
