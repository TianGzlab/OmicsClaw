## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   ├── counts.csv
│   ├── de_results.csv
│   ├── de_significant.csv
│   └── deseq2_results.csv
└── figures/
    ├── de_barplot.png
    ├── ma_plot.png
    ├── pvalue_histogram.png
    └── volcano_plot.png
```

## File contents

- `tables/counts.csv` — written by `bulkrna_de.py` (or its imported `_lib/` helpers).
- `tables/de_results.csv` — written by `bulkrna_de.py` (or its imported `_lib/` helpers).
- `tables/de_significant.csv` — written by `bulkrna_de.py` (or its imported `_lib/` helpers).
- `tables/deseq2_results.csv` — written by `bulkrna_de.py` (or its imported `_lib/` helpers).
- `figures/de_barplot.png` — written by `bulkrna_de.py` (or its imported `_lib/` helpers).
- `figures/ma_plot.png` — written by `bulkrna_de.py` (or its imported `_lib/` helpers).
- `figures/pvalue_histogram.png` — written by `bulkrna_de.py` (or its imported `_lib/` helpers).
- `figures/volcano_plot.png` — written by `bulkrna_de.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_de.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_bulkrna_counts.csv` — generated only on `--demo`.

## Notes

Auto-generated from `bulkrna_de.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
