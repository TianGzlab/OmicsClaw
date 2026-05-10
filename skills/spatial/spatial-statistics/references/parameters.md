<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--analysis-type`
- `--centrality-score`
- `--cluster-key`
- `--coocc-interval`
- `--coocc-n-splits`
- `--genes`
- `--getis-star`
- `--local-moran-geoda-quads`
- `--n-top-genes`
- `--no-getis-star`
- `--no-local-moran-geoda-quads`
- `--no-stats-two-tailed`
- `--ripley-max-dist`
- `--ripley-metric`
- `--ripley-mode`
- `--ripley-n-neigh`
- `--ripley-n-observations`
- `--ripley-n-simulations`
- `--ripley-n-steps`
- `--stats-corr-method`
- `--stats-n-neighs`
- `--stats-n-perms`
- `--stats-n-rings`
- `--stats-seed`
- `--stats-two-tailed`

## Per-method parameter hints

### `bivariate_moran`

**Tuning priority:** genes(exactly two) → stats_n_neighs/stats_n_rings → stats_n_perms

**Core parameters:**

| name | default |
|---|---|
| `genes` | `—` |
| `stats_n_neighs` | `6` |
| `stats_n_rings` | `1` |
| `stats_n_perms` | `199` |

**Requires:**
- `X_log_normalized`
- `obsm.spatial`

**Tips:**
- `bivariate_moran` requires exactly two genes and uses official `esda.Moran_BV`.
- Interpret the result as spatial cross-correlation between neighboring expression patterns, not as a ligand-receptor or coexpression model.

### `co_occurrence`

**Tuning priority:** cluster_key → coocc_interval → coocc_n_splits

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `coocc_interval` | `50` |
| `coocc_n_splits` | `None` |

**Requires:**
- `obs.cluster_key`
- `obsm.spatial`

**Tips:**
- `co_occurrence` is a distance-binned descriptive proximity summary for cluster pairs; it is not a gene-level association test.
- --coocc-interval / --coocc-n-splits: official `squidpy.gr.co_occurrence()` controls exposed by the wrapper.

### `geary`

**Tuning priority:** genes/n_top_genes → stats_n_neighs/stats_n_rings → stats_n_perms/stats_corr_method

**Core parameters:**

| name | default |
|---|---|
| `genes` | `—` |
| `n_top_genes` | `20` |
| `stats_n_neighs` | `6` |
| `stats_n_rings` | `1` |
| `stats_n_perms` | `199` |
| `stats_corr_method` | `fdr_bh` |
| `stats_two_tailed` | `False` |
| `stats_seed` | `123` |

**Requires:**
- `X_log_normalized`
- `obsm.spatial`

**Tips:**
- `geary` runs the same Squidpy global-autocorrelation engine as Moran but with `mode='geary'`.
- Geary's C is most useful when the user wants an alternative geometry for local dissimilarity emphasis rather than a second independent test family.

### `getis_ord`

**Tuning priority:** genes/n_top_genes → stats_n_neighs/stats_n_rings → stats_n_perms → getis_star

**Core parameters:**

| name | default |
|---|---|
| `genes` | `—` |
| `n_top_genes` | `20` |
| `stats_n_neighs` | `6` |
| `stats_n_rings` | `1` |
| `stats_n_perms` | `199` |
| `getis_star` | `True` |
| `stats_seed` | `123` |

**Requires:**
- `X_log_normalized`
- `obsm.spatial`

**Tips:**
- `getis_ord` uses official `esda.G_Local` for local hotspot / coldspot scoring.
- --getis-star: official `G_Local(..., star=...)` switch controlling Gi* vs Gi-style neighborhood treatment.

### `local_moran`

**Tuning priority:** genes/n_top_genes → stats_n_neighs/stats_n_rings → stats_n_perms → local_moran_geoda_quads

**Core parameters:**

| name | default |
|---|---|
| `genes` | `—` |
| `n_top_genes` | `20` |
| `stats_n_neighs` | `6` |
| `stats_n_rings` | `1` |
| `stats_n_perms` | `199` |
| `local_moran_geoda_quads` | `False` |
| `stats_seed` | `123` |

**Requires:**
- `X_log_normalized`
- `obsm.spatial`

**Tips:**
- `local_moran` uses official `esda.Moran_Local` on the Squidpy-derived spatial graph.
- --local-moran-geoda-quads: official `Moran_Local(..., geoda_quads=...)` switch for quadrant labeling convention.

### `moran`

**Tuning priority:** genes/n_top_genes → stats_n_neighs/stats_n_rings → stats_n_perms/stats_corr_method

**Core parameters:**

| name | default |
|---|---|
| `genes` | `—` |
| `n_top_genes` | `20` |
| `stats_n_neighs` | `6` |
| `stats_n_rings` | `1` |
| `stats_n_perms` | `199` |
| `stats_corr_method` | `fdr_bh` |
| `stats_two_tailed` | `False` |
| `stats_seed` | `123` |

**Requires:**
- `X_log_normalized`
- `obsm.spatial`

**Tips:**
- `moran` runs `squidpy.gr.spatial_autocorr(mode='moran')` on the selected genes from `adata.X`.
- --stats-corr-method / --stats-two-tailed / --stats-n-perms / --stats-seed: official `squidpy.gr.spatial_autocorr()` controls.
- If `--genes` is omitted, OmicsClaw uses HVGs first and falls back to high-variance genes.

### `neighborhood_enrichment`

**Tuning priority:** cluster_key → stats_n_neighs/stats_n_rings → stats_n_perms

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `stats_n_neighs` | `6` |
| `stats_n_rings` | `1` |
| `stats_n_perms` | `199` |
| `stats_seed` | `123` |

**Requires:**
- `obs.cluster_key`
- `obsm.spatial`

**Tips:**
- `neighborhood_enrichment` permutes cluster labels on the Squidpy spatial graph; it does not read the expression matrix.
- --stats-n-neighs / --stats-n-rings: core `squidpy.gr.spatial_neighbors()` graph controls exposed directly by the wrapper.
- --stats-n-perms / --stats-seed: official `squidpy.gr.nhood_enrichment()` permutation controls.

### `network_properties`

**Tuning priority:** stats_n_neighs/stats_n_rings → cluster_key(optional)

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `stats_n_neighs` | `6` |
| `stats_n_rings` | `1` |

**Requires:**
- `obsm.spatial`

**Tips:**
- `network_properties` summarizes the Squidpy spatial graph with NetworkX; `cluster_key` only affects optional per-cluster aggregation.
- Graph-density differences across runs are only meaningful if the graph-construction parameters are reported alongside them.

### `ripley`

**Tuning priority:** cluster_key → ripley_mode → ripley_n_simulations/n_observations → ripley_n_steps/max_dist

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `ripley_mode` | `L` |
| `ripley_metric` | `euclidean` |
| `ripley_n_neigh` | `2` |
| `ripley_n_simulations` | `100` |
| `ripley_n_observations` | `1000` |
| `ripley_max_dist` | `None` |
| `ripley_n_steps` | `50` |
| `stats_seed` | `123` |

**Requires:**
- `obs.cluster_key`
- `obsm.spatial`

**Tips:**
- OmicsClaw defaults to Ripley's `L` because it is usually the most interpretable first pass for clustered vs dispersed spatial patterns.
- --ripley-mode / --ripley-metric / --ripley-n-neigh / --ripley-n-simulations / --ripley-n-observations / --ripley-max-dist / --ripley-n-steps / --stats-seed: official `squidpy.gr.ripley()` controls.

### `spatial_centrality`

**Tuning priority:** cluster_key → centrality_score → stats_n_neighs/stats_n_rings

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `centrality_score` | `all` |
| `stats_n_neighs` | `6` |
| `stats_n_rings` | `1` |

**Requires:**
- `obs.cluster_key`
- `obsm.spatial`

**Tips:**
- `spatial_centrality` wraps official `squidpy.gr.centrality_scores()`.
- Current Squidpy output columns are `degree_centrality`, `average_clustering`, and `closeness_centrality`; OmicsClaw keeps that contract instead of inventing extra score names.
