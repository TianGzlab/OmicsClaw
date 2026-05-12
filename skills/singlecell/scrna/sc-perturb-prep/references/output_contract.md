## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── processed.h5ad
├── tables/
│   ├── assignment_status_counts.csv
│   ├── cell_metadata.csv
│   ├── dropped_multi_guide_cells.csv
│   ├── feature_type_summary.csv
│   ├── perturbation_assignments.csv
│   └── perturbation_counts.csv
└── figures/
    └── perturbation_counts.png
```

## File contents

- `tables/assignment_status_counts.csv` — written by `sc_perturb_prep.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_perturb_prep.py` (or its imported `_lib/` helpers).
- `tables/dropped_multi_guide_cells.csv` — written by `sc_perturb_prep.py` (or its imported `_lib/` helpers).
- `tables/feature_type_summary.csv` — written by `sc_perturb_prep.py` (or its imported `_lib/` helpers).
- `tables/perturbation_assignments.csv` — written by `sc_perturb_prep.py` (or its imported `_lib/` helpers).
- `tables/perturbation_counts.csv` — written by `sc_perturb_prep.py` (or its imported `_lib/` helpers).
- `figures/perturbation_counts.png` — written by `sc_perturb_prep.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_perturb_prep.py`.
- `commands.sh` — written by `sc_perturb_prep.py`.
- `processed.h5ad` — written by `sc_perturb_prep.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_perturb_prep.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
