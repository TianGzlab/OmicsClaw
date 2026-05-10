## Output Structure

```
output_directory/
├── report.md
├── result.json
├── 3M-february-2018.txt
├── 737K-august-2016.txt
├── Aligned.sortedByCoord.out.bam
├── analysis_summary.txt
├── commands.sh
├── manifest.json
├── multiqc_report.html
├── possorted_genome_bam.bam
├── processed.h5ad
├── velocity_input.h5ad
├── web_summary.html
├── tables/
│   ├── Summary.csv
│   ├── barcodes.tsv
│   ├── cell_metadata.csv
│   ├── features.tsv
│   ├── genes.tsv
│   ├── metrics_summary.csv
│   ├── top_velocity_genes.csv
│   └── velocity_layer_summary.csv
└── figures/
    ├── velocity_gene_balance.png
    ├── velocity_layer_fraction.png
    ├── velocity_layer_summary.png
    └── velocity_top_genes_stacked.png
```

## File contents

- `tables/Summary.csv` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `tables/barcodes.tsv` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `tables/features.tsv` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `tables/genes.tsv` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `tables/metrics_summary.csv` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `tables/top_velocity_genes.csv` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `tables/velocity_layer_summary.csv` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `figures/velocity_gene_balance.png` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `figures/velocity_layer_fraction.png` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `figures/velocity_layer_summary.png` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `figures/velocity_top_genes_stacked.png` — written by `sc_velocity_prep.py` (or its imported `_lib/` helpers).
- `3M-february-2018.txt` — written by `sc_velocity_prep.py`.
- `737K-august-2016.txt` — written by `sc_velocity_prep.py`.
- `Aligned.sortedByCoord.out.bam` — written by `sc_velocity_prep.py`.
- `analysis_summary.txt` — written by `sc_velocity_prep.py`.
- `commands.sh` — written by `sc_velocity_prep.py`.
- `manifest.json` — written by `sc_velocity_prep.py`.
- `multiqc_report.html` — written by `sc_velocity_prep.py`.
- `possorted_genome_bam.bam` — written by `sc_velocity_prep.py`.
- `processed.h5ad` — written by `sc_velocity_prep.py`.
- `velocity_input.h5ad` — written by `sc_velocity_prep.py`.
- `web_summary.html` — written by `sc_velocity_prep.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_velocity_prep.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
