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
The seven possible PNG outputs and their recipe conditions are:

| File | Required state |
|---|---|
| `figures/spatial_leiden.png` | Leiden labels and spatial coordinates |
| `figures/umap_leiden.png` | Leiden labels and `obsm['X_umap']` |
| `figures/qc_metrics_spatial.png` | Spatial coordinates and at least one QC metric |
| `figures/cluster_size_barplot.png` | A nonempty cluster summary |
| `figures/pca_variance_curve.png` | A nonempty PCA variance table |
| `figures/leiden_resolution_sweep.png` | A nonempty multi-resolution summary from `--resolutions` |
| `figures/qc_metric_distributions.png` | A nonempty QC distribution table |

These conditions match `_build_preprocess_visualization_recipe` in
`spatial_preprocess.py`. A renderer can still fail; consult the manifest
for the files actually produced.

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
