## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── manifest.json
├── omicsclaw_stpipeline_run.json
├── r_visualization.sh
├── raw_counts.h5ad
├── st_pipeline.stderr.txt
├── st_pipeline.stdout.txt
├── tables/
│   ├── gene_qc.csv
│   ├── raw_gene_qc.csv
│   ├── raw_processing_run_summary.csv
│   ├── raw_processing_spatial_points.csv
│   ├── raw_spot_qc.csv
│   ├── raw_top_genes.csv
│   ├── run_summary.csv
│   ├── saturation_curve.csv
│   ├── spatial_coordinates.csv
│   ├── spot_qc.csv
│   ├── stage_summary.csv
│   └── top_genes.csv
└── figures/
    ├── raw_detected_genes_spatial.png
    ├── raw_spot_qc_histograms.png
    ├── raw_top_genes_barplot.png
    ├── raw_total_counts_spatial.png
    ├── st_pipeline_saturation_curve.png
    └── st_pipeline_stage_attrition.png
```

## File contents

- `tables/gene_qc.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/raw_gene_qc.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/raw_processing_run_summary.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/raw_processing_spatial_points.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/raw_spot_qc.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/raw_top_genes.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/run_summary.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/saturation_curve.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/spatial_coordinates.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/spot_qc.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/stage_summary.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `tables/top_genes.csv` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `figures/raw_detected_genes_spatial.png` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `figures/raw_spot_qc_histograms.png` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `figures/raw_top_genes_barplot.png` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `figures/raw_total_counts_spatial.png` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `figures/st_pipeline_saturation_curve.png` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `figures/st_pipeline_stage_attrition.png` — written by `spatial_raw_processing.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_raw_processing.py`.
- `manifest.json` — written by `spatial_raw_processing.py`.
- `omicsclaw_stpipeline_run.json` — written by `spatial_raw_processing.py`.
- `r_visualization.sh` — written by `spatial_raw_processing.py`.
- `raw_counts.h5ad` — written by `spatial_raw_processing.py`.
- `st_pipeline.stderr.txt` — written by `spatial_raw_processing.py`.
- `st_pipeline.stdout.txt` — written by `spatial_raw_processing.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_raw_processing.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
