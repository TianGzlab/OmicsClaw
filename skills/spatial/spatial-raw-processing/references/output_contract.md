# CLI-only output contract

ST-Pipeline is an external FASTQ workflow. Steps invoke this skill with run_cli;
there is no in-memory _api.py. Demo mode creates synthetic upstream outputs
and checks conversion/reporting, not FASTQ alignment.

## Outputs

- `raw_counts.h5ad`: raw counts in X, layers['counts'] and raw; spatial coordinates
  in obsm['spatial']. No normalization or clustering has run.
- `report.md` and `result.json`: input, method, parameters and upstream statistics.
- Always exported tables: `tables/run_summary.csv`, `tables/stage_summary.csv`,
  `tables/spot_qc.csv`, `tables/gene_qc.csv`, `tables/top_genes.csv`.
- `tables/spatial_coordinates.csv` requires coordinate data;
  `tables/saturation_curve.csv` requires upstream saturation metrics.
- Plot data: `figure_data/raw_processing_run_summary.csv`, `figure_data/stage_summary.csv`,
  `figure_data/raw_spot_qc.csv`, `figure_data/raw_gene_qc.csv`, `figure_data/raw_top_genes.csv`.
- `figure_data/raw_processing_spatial_points.csv` and `figure_data/saturation_curve.csv`
  require coordinate/saturation data respectively.
- `figures/manifest.json` and `figure_data/manifest.json` inventory the gallery.
- `reproducibility/commands.sh`, `reproducibility/requirements.txt`,
  `reproducibility/r_visualization.sh` record CLI and rendering instructions.

## Figures

- `figures/raw_total_counts_spatial.png` and `figures/raw_detected_genes_spatial.png`:
  available coordinates and spot QC.
- `figures/raw_spot_qc_histograms.png`: nonempty spot metrics.
- `figures/raw_top_genes_barplot.png`: nonempty gene metrics.
- `figures/st_pipeline_stage_attrition.png`: upstream stage metrics.
- `figures/st_pipeline_saturation_curve.png`: upstream saturation metrics.

Real pipeline runs may also produce `omicsclaw_stpipeline_run.json`,
`st_pipeline.stdout.txt`, `st_pipeline.stderr.txt` and native count/log files.
The synthetic demo does not promise these real-process logs.
The next analysis step is spatial-preprocess on raw_counts.h5ad.
