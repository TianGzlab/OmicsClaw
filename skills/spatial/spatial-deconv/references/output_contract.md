# Output contract

The function library returns the same spatial AnnData with a method-specific
obsm['deconvolution_<method>'] matrix and uns cell-type labels. Reference data
are copied. proportions returns an observation-indexed DataFrame; the figure
function returns a matplotlib Figure without saving it. run_info(keep=False)
removes the JSON library diagnostic record before CLI serialization.

## CLI files

Successful runs write processed.h5ad, report.md, result.json, commands.sh,
requirements.txt and r_visualization.sh. Tables include:

- tables/proportions.csv: spot identifier and cell-type proportion columns.
- tables/dominant_celltype.csv: highest-proportion cell type per spot.
- tables/celltype_diversity.csv: Shannon and normalized entropy.
- tables/mean_proportions.csv: mean composition across spots.
- tables/deconv_spot_metrics.csv: dominance, entropy and assignment margin.
- tables/dominant_celltype_counts.csv: count of spots assigned to each type.
- tables/card_refined_proportions.csv: only when CARD returns imputation results.

The same gallery inputs are under figure_data/, with deconv_run_summary.csv,
conditional deconv_spatial_points.csv/deconv_umap_points.csv and manifest.json.
R exchange CSVs live in temporary directories and are not permanent outputs.

## Figures

Each requires its source values and successful rendering:

- figures/spatial_proportions.png: per-type spatial proportions.
- figures/dominant_celltype.png: spatial dominant labels.
- figures/celltype_diversity.png: spatial entropy.
- figures/umap_proportions.png: when UMAP coordinates are available.
- figures/assignment_margin_spatial.png: spatial assignment margin.
- figures/mean_proportions.png: average composition.
- figures/dominant_celltype_distribution.png: dominant-label counts.
- figures/assignment_margin_distribution.png: assignment-margin distribution.

Gallery diagnostics are added to obs by the CLI, including dominant labels,
proportions and entropy. The function library retains the proportion matrix;
it does not generate the report gallery as a side effect.
