## Output Structure

```
output_directory/
├── report.md
├── result.json
├── 3M-february-2018.txt
├── 737K-august-2016.txt
├── Aligned.sortedByCoord.out.bam
├── analysis_summary.txt
├── cells_x_genes.barcodes.txt
├── cells_x_genes.genes.txt
├── commands.sh
├── manifest.json
├── multiqc_report.html
├── possorted_genome_bam.bam
├── processed.h5ad
├── quants_mat_cols.txt
├── quants_mat_rows.txt
├── simpleaf_index.json
├── standardized_input.h5ad
├── web_summary.html
├── tables/
│   ├── Summary.csv
│   ├── backend_summary.csv
│   ├── barcode_metrics.csv
│   ├── barcodes.tsv
│   ├── cell_metadata.csv
│   ├── count_summary.csv
│   ├── features.tsv
│   ├── genes.tsv
│   ├── metrics_summary.csv
│   └── simpleaf_t2g.tsv
└── figures/
    ├── barcode_rank.png
    ├── count_complexity_scatter.png
    └── count_distributions.png
```

## File contents

- `tables/Summary.csv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `tables/backend_summary.csv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `tables/barcode_metrics.csv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `tables/barcodes.tsv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `tables/count_summary.csv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `tables/features.tsv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `tables/genes.tsv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `tables/metrics_summary.csv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `tables/simpleaf_t2g.tsv` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `figures/barcode_rank.png` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `figures/count_complexity_scatter.png` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `figures/count_distributions.png` — written by `sc_count.py` (or its imported `_lib/` helpers).
- `3M-february-2018.txt` — written by `sc_count.py`.
- `737K-august-2016.txt` — written by `sc_count.py`.
- `Aligned.sortedByCoord.out.bam` — written by `sc_count.py`.
- `analysis_summary.txt` — written by `sc_count.py`.
- `cells_x_genes.barcodes.txt` — written by `sc_count.py`.
- `cells_x_genes.genes.txt` — written by `sc_count.py`.
- `commands.sh` — written by `sc_count.py`.
- `manifest.json` — written by `sc_count.py`.
- `multiqc_report.html` — written by `sc_count.py`.
- `possorted_genome_bam.bam` — written by `sc_count.py`.
- `processed.h5ad` — written by `sc_count.py`.
- `quants_mat_cols.txt` — written by `sc_count.py`.
- `quants_mat_rows.txt` — written by `sc_count.py`.
- `simpleaf_index.json` — written by `sc_count.py`.
- `standardized_input.h5ad` — written by `sc_count.py`.
- `web_summary.html` — written by `sc_count.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_count.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
