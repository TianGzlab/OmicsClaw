# Output contract

Functions return the same annotated AnnData, a DataFrame or a Figure. Library
diagnostics are JSON in uns; run_info(keep=False) removes them for CLI output.

The CLI always writes processed.h5ad, report.md, result.json, commands.sh,
requirements.txt and r_visualization.sh. Gallery data have a figure_data/manifest.json.

## Tables

- tables/annotation_summary.csv and tables/cell_type_assignments.csv: label counts, percentages and per-observation assignments.
- tables/cluster_annotations.csv and tables/marker_overlap_scores.csv: marker_based only.
- figure_data/annotation_cell_type_counts.csv: label counts for the gallery.
- figure_data/annotation_spatial_points.csv and figure_data/annotation_umap_points.csv: when the corresponding coordinates exist.
- figure_data/annotation_probabilities.csv: when Tangram, scANVI or CellAssign returns probabilities.
- figure_data/marker_overlap_scores.csv: when marker overlap is available.

## Figures

The gallery records attempted plots and failures in its manifest. Files are
conditional on their input data and successful rendering:

- figures/cell_type_barplot.png: label counts.
- figures/cell_type_spatial.png: spatial coordinates.
- figures/cell_type_umap.png: UMAP coordinates.
- figures/marker_overlap_heatmap.png: marker overlap matrix.
- figures/annotation_probability_heatmap.png: probability matrix.
- figures/annotation_confidence_histogram.png: confidence values.
- figures/annotation_confidence_spatial.png: confidence values and spatial coordinates.

Marker labels are in obs['cell_type']. Tangram probabilities are in
tangram_ct_pred; scANVI and CellAssign have their own probability matrices
and confidence columns. These slots are method-dependent.
