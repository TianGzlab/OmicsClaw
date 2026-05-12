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
│   ├── gene_expression.csv
│   ├── program_correlation.csv
│   ├── program_tpm.csv
│   ├── program_usage.csv
│   ├── program_weights.csv
│   └── top_program_genes.csv
└── figures/
    ├── mean_program_usage.png
    ├── program_correlation.png
    ├── r_feature_cor.png
    └── r_feature_violin.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `tables/gene_expression.csv` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `tables/program_correlation.csv` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `tables/program_tpm.csv` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `tables/program_usage.csv` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `tables/program_weights.csv` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `tables/top_program_genes.csv` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `figures/mean_program_usage.png` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `figures/program_correlation.png` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `figures/r_feature_cor.png` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `figures/r_feature_violin.png` — written by `sc_gene_programs.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_gene_programs.py`.
- `manifest.json` — written by `sc_gene_programs.py`.
- `processed.h5ad` — written by `sc_gene_programs.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_gene_programs.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
