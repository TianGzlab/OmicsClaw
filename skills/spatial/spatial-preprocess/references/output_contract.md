# Spatial preprocessing outputs

The CLI writes these files beneath its `--output` directory. Notebook
functions return objects; a step chooses its own output paths with
`write_output`, such as `intermediate/processed.h5ad`.

## Data and reports

- `processed.h5ad`: log-normalized `X`; filtered raw counts in `raw` and
  `layers['counts']`; QC metrics and Leiden labels in `obs`; HVGs in `var`;
  PCA, UMAP and any input spatial coordinates in `obsm`; the neighbor graph
  in `obsp`. The CLI removes the library's JSON run diagnostic before saving.
- `report.md` and `result.json`: run summary, effective parameters and gallery metadata.
- `tables/cluster_summary.csv`: cluster labels and spot counts.
- `tables/qc_summary.csv`: input and filtered dimensions, HVGs, clusters and PC counts.
- `tables/pca_variance_ratio.csv`: per-PC variance and cumulative variance ratio.
- `tables/multi_resolution_summary.csv`: written only for a resolution sweep.

## Gallery

`figures/manifest.json` records which plots rendered or were skipped.
The recipe includes cluster sizes, PCA variance, QC distributions, UMAP
and spatial Leiden plots. Spatial plots need coordinates; the resolution
sweep plot needs `--resolutions`. See `_build_preprocess_visualization_recipe`
in `spatial_preprocess.py` for individual plot conditions.

`figure_data/manifest.json` names the exported plot data:

- `cluster_summary.csv`, `qc_metric_distributions.csv`,
  `preprocess_run_summary.csv` and `pca_variance_ratio.csv`.
- `multi_resolution_summary.csv` only for a resolution sweep.
- `preprocess_spatial_points.csv` only when coordinates are present.
- `preprocess_umap_points.csv` when the UMAP embedding is present.

These point and distribution tables live in `figure_data/`, not `tables/`.

## Reproducibility files

`reproducibility/commands.sh` records effective CLI parameters.
`reproducibility/environment.txt` lists available package versions.
`reproducibility/r_visualization.sh` invokes the optional R renderer.

The `--demo` input is loaded from `examples/demo_visium.h5ad` when present,
otherwise generated in memory. The skill does not write a demo input
file into the output directory.
