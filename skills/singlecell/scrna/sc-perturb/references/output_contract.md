## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── manifest.json
├── processed.h5ad
├── tables/
│   ├── cell_metadata.csv
│   ├── cell_type_counts.csv
│   ├── mixscape_cell_classes.csv
│   ├── mixscape_class_counts.csv
│   ├── mixscape_global_class_counts.csv
│   └── mixscape_global_classes.csv
└── figures/
    ├── mixscape_global_classes.png
    └── r_perturbation_barplot.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_perturb.py` (or its imported `_lib/` helpers).
- `tables/cell_type_counts.csv` — written by `sc_perturb.py` (or its imported `_lib/` helpers).
- `tables/mixscape_cell_classes.csv` — written by `sc_perturb.py` (or its imported `_lib/` helpers).
- `tables/mixscape_class_counts.csv` — written by `sc_perturb.py` (or its imported `_lib/` helpers).
- `tables/mixscape_global_class_counts.csv` — written by `sc_perturb.py` (or its imported `_lib/` helpers).
- `tables/mixscape_global_classes.csv` — written by `sc_perturb.py` (or its imported `_lib/` helpers).
- `figures/mixscape_global_classes.png` — written by `sc_perturb.py` (or its imported `_lib/` helpers).
- `figures/r_perturbation_barplot.png` — written by `sc_perturb.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_perturb.py`.
- `commands.sh` — written by `sc_perturb.py`.
- `manifest.json` — written by `sc_perturb.py`.
- `processed.h5ad` — written by `sc_perturb.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_perturb.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
