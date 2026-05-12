## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── manifest.json
├── processed.h5ad
├── tables/
│   ├── cell_metadata.csv
│   ├── de_top_markers.csv
│   ├── diff_regulation.csv
│   ├── matrix.csv
│   └── tenifold_diff_regulation.csv
└── figures/
    ├── pvalue_distribution.png
    ├── r_isp_volcano.png
    └── top_perturbed_genes.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_in_silico_perturbation.py` (or its imported `_lib/` helpers).
- `tables/de_top_markers.csv` — written by `sc_in_silico_perturbation.py` (or its imported `_lib/` helpers).
- `tables/diff_regulation.csv` — written by `sc_in_silico_perturbation.py` (or its imported `_lib/` helpers).
- `tables/matrix.csv` — written by `sc_in_silico_perturbation.py` (or its imported `_lib/` helpers).
- `tables/tenifold_diff_regulation.csv` — written by `sc_in_silico_perturbation.py` (or its imported `_lib/` helpers).
- `figures/pvalue_distribution.png` — written by `sc_in_silico_perturbation.py` (or its imported `_lib/` helpers).
- `figures/r_isp_volcano.png` — written by `sc_in_silico_perturbation.py` (or its imported `_lib/` helpers).
- `figures/top_perturbed_genes.png` — written by `sc_in_silico_perturbation.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_in_silico_perturbation.py`.
- `manifest.json` — written by `sc_in_silico_perturbation.py`.
- `processed.h5ad` — written by `sc_in_silico_perturbation.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_in_silico_perturbation.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
