## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   ├── cell_fractions.csv
│   └── pseudotime_estimates.csv
└── figures/
    ├── bulk_on_trajectory.png
    ├── fraction_heatmap.png
    ├── pseudotime_distribution.png
    └── trajectory_embedding.png
```

## File contents

- `tables/cell_fractions.csv` — written by `bulkrna_trajblend.py` (or its imported `_lib/` helpers).
- `tables/pseudotime_estimates.csv` — written by `bulkrna_trajblend.py` (or its imported `_lib/` helpers).
- `figures/bulk_on_trajectory.png` — written by `bulkrna_trajblend.py` (or its imported `_lib/` helpers).
- `figures/fraction_heatmap.png` — written by `bulkrna_trajblend.py` (or its imported `_lib/` helpers).
- `figures/pseudotime_distribution.png` — written by `bulkrna_trajblend.py` (or its imported `_lib/` helpers).
- `figures/trajectory_embedding.png` — written by `bulkrna_trajblend.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_trajblend.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `bulkrna_trajblend.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
