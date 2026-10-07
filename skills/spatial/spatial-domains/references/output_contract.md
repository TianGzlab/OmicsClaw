# Output contract

Functions return the same AnnData with spatial_domain labels, a domain-count
DataFrame or a Figure. run_info(keep=False) removes library diagnostics before
CLI serialization.

The CLI writes processed.h5ad, report.md, result.json, commands.sh,
requirements.txt and r_visualization.sh. figure_data/manifest.json records
which gallery inputs and rendered outputs are available.

## Tables

- tables/domain_summary.csv: per-domain counts and percentages.
- tables/domain_assignments.csv: observation labels and local purity when computed.
- tables/domain_neighbor_mixing.csv: when spatial neighbor diagnostics exist.
- figure_data/domain_counts.csv: gallery counts.
- figure_data/domain_spatial_points.csv: when spatial coordinates exist.
- figure_data/domain_umap_points.csv: when UMAP exists.
- figure_data/domain_method_embedding_points.csv: when a backend embedding has at least two components.
- figure_data/domain_neighbor_mixing.csv: when neighbor mixing is computed.

## Figures

These files depend on available coordinates/diagnostics and successful rendering:

- figures/domain_sizes.png: domain counts.
- figures/spatial_domains.png: spatial coordinates.
- figures/umap_domains.png: UMAP.
- figures/pca_domains.png: PCA fallback embedding.
- figures/domain_local_purity_spatial.png: spatial coordinates and local purity.
- figures/domain_local_purity_histogram.png: local purity values.
- figures/domain_neighbor_mixing.png: domain neighbor mixing matrix.

Backend embeddings include X_stagate, X_graphst, X_banksy_pca and X_cellcharter;
only the selected backend's embedding is required. Domain labels are always
obs['spatial_domain'] after successful identification.
