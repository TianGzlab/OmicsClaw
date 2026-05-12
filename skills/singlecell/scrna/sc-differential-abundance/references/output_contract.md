## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── annotated_input.h5ad
├── commands.sh
├── manifest.json
├── processed.h5ad
├── tables/
│   ├── cell_meta.csv
│   ├── cell_metadata.csv
│   ├── condition_mean_proportions.csv
│   ├── milo_nhood_results.csv
│   ├── proportion_test_results.csv
│   ├── sample_by_celltype_counts.csv
│   ├── sample_by_celltype_proportions.csv
│   ├── sccoda_effects.csv
│   └── simple_da_results.csv
└── figures/
    ├── milo_logfc_barplot.png
    ├── proportion_test_r_no_results.png
    ├── r_cell_barplot.png
    ├── r_cell_density.png
    ├── r_embedding_discrete.png
    ├── r_proportion_test.png
    ├── sample_celltype_proportions.png
    └── sccoda_log2fc_barplot.png
```

## File contents

- `tables/cell_meta.csv` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `tables/condition_mean_proportions.csv` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `tables/milo_nhood_results.csv` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `tables/proportion_test_results.csv` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `tables/sample_by_celltype_counts.csv` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `tables/sample_by_celltype_proportions.csv` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `tables/sccoda_effects.csv` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `tables/simple_da_results.csv` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `figures/milo_logfc_barplot.png` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `figures/proportion_test_r_no_results.png` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `figures/r_cell_barplot.png` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `figures/r_cell_density.png` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_discrete.png` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `figures/r_proportion_test.png` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `figures/sample_celltype_proportions.png` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `figures/sccoda_log2fc_barplot.png` — written by `sc_differential_abundance.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_differential_abundance.py`.
- `annotated_input.h5ad` — written by `sc_differential_abundance.py`.
- `commands.sh` — written by `sc_differential_abundance.py`.
- `manifest.json` — written by `sc_differential_abundance.py`.
- `processed.h5ad` — written by `sc_differential_abundance.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_differential_abundance.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
