## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── environment.txt
├── manifest.json
├── processed.h5ad
├── r_visualization.sh
├── tables/
│   ├── registration_disparities.csv
│   ├── registration_metrics.csv
│   ├── registration_points.csv
│   ├── registration_run_summary.csv
│   ├── registration_shift_by_slice.csv
│   └── registration_summary.csv
└── figures/
    ├── registration_disparities.png
    ├── registration_shift_by_slice.png
    ├── registration_shift_distribution.png
    ├── registration_shift_map.png
    ├── slices_after.png
    └── slices_before.png
```

## File contents

- `tables/registration_disparities.csv` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `tables/registration_metrics.csv` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `tables/registration_points.csv` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `tables/registration_run_summary.csv` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `tables/registration_shift_by_slice.csv` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `tables/registration_summary.csv` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `figures/registration_disparities.png` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `figures/registration_shift_by_slice.png` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `figures/registration_shift_distribution.png` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `figures/registration_shift_map.png` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `figures/slices_after.png` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `figures/slices_before.png` — written by `spatial_register.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_register.py`.
- `environment.txt` — written by `spatial_register.py`.
- `manifest.json` — written by `spatial_register.py`.
- `processed.h5ad` — written by `spatial_register.py`.
- `r_visualization.sh` — written by `spatial_register.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_register.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
