# Singlecell Output Contract

This file defines the recommended output layout for scRNA skills.

## Baseline Layout

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
├── tables/
├── figure_data/
└── reproducibility/
```

## Required Semantics

- `processed.h5ad`
  - must be the downstream-facing object
  - must include `omicsclaw_input_contract`
  - must include `omicsclaw_matrix_contract`

- `figures/`
  - canonical quick-look gallery
  - users should be able to understand the analysis without reading code first

- `tables/`
  - human- and analysis-friendly structured exports

- `figure_data/`
  - plot-ready data for downstream customization
  - should not recompute the science

## Singlecell-Specific Rule

Do not write a count-oriented object and describe it as if it were already normalized.
Do not write a normalized object and forget to preserve raw counts.

Every skill that writes AnnData should make its matrix state explicit in both:
- `report.md`
- `result.json.data.matrix_contract`
