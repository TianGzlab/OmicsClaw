## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── requirements.txt
├── spatial_microenvironment_subset.h5ad
├── tables/
│   ├── center_observations.csv
│   ├── label_composition.csv
│   ├── selected_observations.csv
│   └── selection_summary.csv
└── figures/
    └── microenvironment_selection.png
```

## File contents

- `tables/center_observations.csv` — written by `spatial_microenvironment_subset.py` (or its imported `_lib/` helpers).
- `tables/label_composition.csv` — written by `spatial_microenvironment_subset.py` (or its imported `_lib/` helpers).
- `tables/selected_observations.csv` — written by `spatial_microenvironment_subset.py` (or its imported `_lib/` helpers).
- `tables/selection_summary.csv` — written by `spatial_microenvironment_subset.py` (or its imported `_lib/` helpers).
- `figures/microenvironment_selection.png` — written by `spatial_microenvironment_subset.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_microenvironment_subset.py`.
- `requirements.txt` — written by `spatial_microenvironment_subset.py`.
- `spatial_microenvironment_subset.h5ad` — written by `spatial_microenvironment_subset.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_visium.h5ad` — generated only on `--demo`.

## Notes

Auto-generated from `spatial_microenvironment_subset.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
