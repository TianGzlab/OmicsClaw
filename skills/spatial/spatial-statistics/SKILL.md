---
name: spatial-statistics
description: >-
  Spatial statistics for spatial transcriptomics using neighborhood enrichment,
  Ripley's statistics, co-occurrence, Moran/Geary autocorrelation, local Moran,
  Getis-Ord Gi*, bivariate Moran, and spatial graph centrality summaries.
version: 0.5.0
author: OmicsClaw Team
license: MIT
tags: [spatial, statistics, moran, geary, ripley, co-occurrence, getis-ord, centrality]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--analysis-type"
    - "--centrality-score"
    - "--cluster-key"
    - "--coocc-interval"
    - "--coocc-n-splits"
    - "--genes"
    - "--getis-star"
    - "--local-moran-geoda-quads"
    - "--n-top-genes"
    - "--no-getis-star"
    - "--no-local-moran-geoda-quads"
    - "--no-stats-two-tailed"
    - "--ripley-max-dist"
    - "--ripley-metric"
    - "--ripley-mode"
    - "--ripley-n-neigh"
    - "--ripley-n-observations"
    - "--ripley-n-simulations"
    - "--ripley-n-steps"
    - "--stats-corr-method"
    - "--stats-n-neighs"
    - "--stats-n-perms"
    - "--stats-n-rings"
    - "--stats-seed"
    - "--stats-two-tailed"
    param_hints:
      neighborhood_enrichment:
        priority: "cluster_key → stats_n_neighs/stats_n_rings → stats_n_perms"
        params: ["cluster_key", "stats_n_neighs", "stats_n_rings", "stats_n_perms",
          "stats_seed"]
        defaults: {cluster_key: "leiden", stats_n_neighs: 6, stats_n_rings: 1, stats_n_perms: 199,
          stats_seed: 123}
        requires: ["obs.cluster_key", "obsm.spatial"]
        tips:
        - "`neighborhood_enrichment` permutes cluster labels on the Squidpy spatial
          graph; it does not read the expression matrix."
        - "--stats-n-neighs / --stats-n-rings: core `squidpy.gr.spatial_neighbors()`
          graph controls exposed directly by the wrapper."
        - "--stats-n-perms / --stats-seed: official `squidpy.gr.nhood_enrichment()`
          permutation controls."
      ripley:
        priority: "cluster_key → ripley_mode → ripley_n_simulations/n_observations
          → ripley_n_steps/max_dist"
        params: ["cluster_key", "ripley_mode", "ripley_metric", "ripley_n_neigh",
          "ripley_n_simulations", "ripley_n_observations", "ripley_max_dist", "ripley_n_steps",
          "stats_seed"]
        defaults: {cluster_key: "leiden", ripley_mode: "L", ripley_metric: "euclidean",
          ripley_n_neigh: 2, ripley_n_simulations: 100, ripley_n_observations: 1000,
          ripley_max_dist: null, ripley_n_steps: 50, stats_seed: 123}
        requires: ["obs.cluster_key", "obsm.spatial"]
        tips:
        - "OmicsClaw defaults to Ripley's `L` because it is usually the most interpretable
          first pass for clustered vs dispersed spatial patterns."
        - "--ripley-mode / --ripley-metric / --ripley-n-neigh / --ripley-n-simulations
          / --ripley-n-observations / --ripley-max-dist / --ripley-n-steps / --stats-seed:
          official `squidpy.gr.ripley()` controls."
      co_occurrence:
        priority: "cluster_key → coocc_interval → coocc_n_splits"
        params: ["cluster_key", "coocc_interval", "coocc_n_splits"]
        defaults: {cluster_key: "leiden", coocc_interval: 50, coocc_n_splits: null}
        requires: ["obs.cluster_key", "obsm.spatial"]
        tips:
        - "`co_occurrence` is a distance-binned descriptive proximity summary for
          cluster pairs; it is not a gene-level association test."
        - "--coocc-interval / --coocc-n-splits: official `squidpy.gr.co_occurrence()`
          controls exposed by the wrapper."
      moran:
        priority: "genes/n_top_genes → stats_n_neighs/stats_n_rings → stats_n_perms/stats_corr_method"
        params: ["genes", "n_top_genes", "stats_n_neighs", "stats_n_rings", "stats_n_perms",
          "stats_corr_method", "stats_two_tailed", "stats_seed"]
        defaults: {n_top_genes: 20, stats_n_neighs: 6, stats_n_rings: 1, stats_n_perms: 199,
          stats_corr_method: "fdr_bh", stats_two_tailed: false, stats_seed: 123}
        requires: ["X_log_normalized", "obsm.spatial"]
        tips:
        - "`moran` runs `squidpy.gr.spatial_autocorr(mode='moran')` on the selected
          genes from `adata.X`."
        - "--stats-corr-method / --stats-two-tailed / --stats-n-perms / --stats-seed:
          official `squidpy.gr.spatial_autocorr()` controls."
        - "If `--genes` is omitted, OmicsClaw uses HVGs first and falls back to high-variance
          genes."
      geary:
        priority: "genes/n_top_genes → stats_n_neighs/stats_n_rings → stats_n_perms/stats_corr_method"
        params: ["genes", "n_top_genes", "stats_n_neighs", "stats_n_rings", "stats_n_perms",
          "stats_corr_method", "stats_two_tailed", "stats_seed"]
        defaults: {n_top_genes: 20, stats_n_neighs: 6, stats_n_rings: 1, stats_n_perms: 199,
          stats_corr_method: "fdr_bh", stats_two_tailed: false, stats_seed: 123}
        requires: ["X_log_normalized", "obsm.spatial"]
        tips:
        - "`geary` runs the same Squidpy global-autocorrelation engine as Moran but
          with `mode='geary'`."
        - "Geary's C is most useful when the user wants an alternative geometry for
          local dissimilarity emphasis rather than a second independent test family."
      local_moran:
        priority: "genes/n_top_genes → stats_n_neighs/stats_n_rings → stats_n_perms
          → local_moran_geoda_quads"
        params: ["genes", "n_top_genes", "stats_n_neighs", "stats_n_rings", "stats_n_perms",
          "local_moran_geoda_quads", "stats_seed"]
        defaults: {n_top_genes: 20, stats_n_neighs: 6, stats_n_rings: 1, stats_n_perms: 199,
          local_moran_geoda_quads: false, stats_seed: 123}
        requires: ["X_log_normalized", "obsm.spatial"]
        tips:
        - "`local_moran` uses official `esda.Moran_Local` on the Squidpy-derived spatial
          graph."
        - "--local-moran-geoda-quads: official `Moran_Local(..., geoda_quads=...)`
          switch for quadrant labeling convention."
      getis_ord:
        priority: "genes/n_top_genes → stats_n_neighs/stats_n_rings → stats_n_perms
          → getis_star"
        params: ["genes", "n_top_genes", "stats_n_neighs", "stats_n_rings", "stats_n_perms",
          "getis_star", "stats_seed"]
        defaults: {n_top_genes: 20, stats_n_neighs: 6, stats_n_rings: 1, stats_n_perms: 199,
          getis_star: true, stats_seed: 123}
        requires: ["X_log_normalized", "obsm.spatial"]
        tips:
        - "`getis_ord` uses official `esda.G_Local` for local hotspot / coldspot scoring."
        - "--getis-star: official `G_Local(..., star=...)` switch controlling Gi*
          vs Gi-style neighborhood treatment."
      bivariate_moran:
        priority: "genes(exactly two) → stats_n_neighs/stats_n_rings → stats_n_perms"
        params: ["genes", "stats_n_neighs", "stats_n_rings", "stats_n_perms"]
        defaults: {stats_n_neighs: 6, stats_n_rings: 1, stats_n_perms: 199}
        requires: ["X_log_normalized", "obsm.spatial"]
        tips:
        - "`bivariate_moran` requires exactly two genes and uses official `esda.Moran_BV`."
        - "Interpret the result as spatial cross-correlation between neighboring expression
          patterns, not as a ligand-receptor or coexpression model."
      network_properties:
        priority: "stats_n_neighs/stats_n_rings → cluster_key(optional)"
        params: ["cluster_key", "stats_n_neighs", "stats_n_rings"]
        defaults: {cluster_key: "leiden", stats_n_neighs: 6, stats_n_rings: 1}
        requires: ["obsm.spatial"]
        tips:
        - "`network_properties` summarizes the Squidpy spatial graph with NetworkX;
          `cluster_key` only affects optional per-cluster aggregation."
        - "Graph-density differences across runs are only meaningful if the graph-construction
          parameters are reported alongside them."
      spatial_centrality:
        priority: "cluster_key → centrality_score → stats_n_neighs/stats_n_rings"
        params: ["cluster_key", "centrality_score", "stats_n_neighs", "stats_n_rings"]
        defaults: {cluster_key: "leiden", centrality_score: "all", stats_n_neighs: 6,
          stats_n_rings: 1}
        requires: ["obs.cluster_key", "obsm.spatial"]
        tips:
        - "`spatial_centrality` wraps official `squidpy.gr.centrality_scores()`."
        - "Current Squidpy output columns are `degree_centrality`, `average_clustering`,
          and `closeness_centrality`; OmicsClaw keeps that contract instead of inventing
          extra score names."
    legacy_aliases: [statistics]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
      - python3
      env: []
      config: []
    emoji: "📊"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
    - kind: pip
      package: squidpy
      bins: []
    - kind: pip
      package: esda
      bins: []
    - kind: pip
      package: libpysal
      bins: []
    - kind: pip
      package: networkx
      bins: []
    trigger_keywords:
    - spatial statistics
    - Moran
    - Geary
    - Ripley
    - co-occurrence
    - Getis-Ord
    - local Moran
    - centrality
    script: spatial_statistics.py
---

# 📊 Spatial Statistics

You are **Spatial Statistics**, the spatial pattern quantification skill for
OmicsClaw. Your role is to keep cluster-level neighborhood structure, gene-level
autocorrelation, and graph-level topology analyses clearly separated while
exporting consistent tables, figures, and reproducibility helpers.

## Why This Exists

- **Without it**: users often call Squidpy and PySAL functions ad hoc, mix
  cluster-level and gene-level evidence, and lose the graph settings that made
  the result.
- **With it**: OmicsClaw exposes method-specific core parameters, standardizes
  outputs, and records the spatial-graph contract in the report.
- **Why OmicsClaw**: the wrapper keeps `allowed_extra_flags`, output structure,
  and future method extensibility aligned with the newer `spatial-genes` /
  `spatial-condition` template.

## Core Capability Groups

1. **Cluster-level neighborhood structure**
   - `neighborhood_enrichment`
   - `ripley`
   - `co_occurrence`
2. **Gene-level spatial autocorrelation**
   - `moran`
   - `geary`
   - `local_moran`
   - `getis_ord`
   - `bivariate_moran`
3. **Spatial graph topology**
   - `network_properties`
   - `spatial_centrality`

## Input Convention

| Input slot | Used by | Notes |
|---|---|---|
| `adata.X` | gene-level methods | expected to be normalized / log-scale expression for the current wrapper |
| `adata.obsm["spatial"]` | all methods | required spatial coordinates |
| `adata.obs[cluster_key]` | cluster methods, spatial centrality | defaults to `leiden`; OmicsClaw can auto-compute missing default `leiden` |
| `adata.obsp["spatial_connectivities"]` | graph-based methods | reused if present, or rebuilt with wrapper parameters |

## Workflow

1. **Load** the preprocessed h5ad.
2. **Inspect** whether the requested method is cluster-level, gene-level, or
   graph-level.
3. **Resolve graph settings** when the method depends on a spatial graph.
4. **Run the statistic** with method-specific core parameters only.
5. **Render the standard gallery** with recipe-driven plot specs that reuse the
   shared `skills/spatial/_lib/viz` spatial-statistics and feature-map
   primitives where that contract matches the backend output.
6. **Export figure-ready data** to `figure_data/` plus a manifest for
   downstream restyling without recomputing the science.
7. **Export** report, result JSON, figures, tables, `processed.h5ad`, and the
   reproducibility bundle.

## Visualization Contract

OmicsClaw treats `spatial-statistics` visualization as a two-layer system:

1. **Python standard gallery**: the canonical result layer. This is the
   default output users should inspect first.
2. **R customization layer**: an optional styling layer that reads
   `figure_data/` and does not rerun Squidpy / PySAL / NetworkX analyses.

Where possible, the standard gallery reuses shared `_lib/viz` renderers:

- `plot_spatial_stats(...)` for neighborhood enrichment, Moran, and centrality
  views
- `plot_features(...)` for local-statistic spot maps and supporting spatial
  context views

Current gallery roles include:

- `overview`: the main analysis figure for the selected statistic
- `supporting`: compact summary views of top pairs, clusters, or genes
- `diagnostic`: score-vs-significance views for applicable global statistics
- `uncertainty`: p-value or statistic-distribution summaries

## CLI Reference

```bash
# Default neighborhood enrichment
oc run spatial-statistics \
  --input <processed.h5ad> --output <dir>

# Ripley's L with more simulations
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type ripley \
  --ripley-mode L --ripley-n-simulations 200 --ripley-n-steps 60 \
  --output <dir>

# Co-occurrence with custom distance-bin count
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type co_occurrence \
  --coocc-interval 80 --output <dir>

# Global Moran's I for a curated gene list
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type moran \
  --genes "EPCAM,VIM,CD3D" \
  --stats-n-neighs 8 --stats-n-perms 499 --stats-corr-method fdr_bh \
  --output <dir>

# Global Geary's C on top variable genes
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type geary \
  --n-top-genes 50 --stats-two-tailed --output <dir>

# Local Moran hotspots
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type local_moran \
  --genes "EPCAM,CD3D" --stats-n-perms 499 \
  --output <dir>

# Getis-Ord Gi*
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type getis_ord \
  --genes "CXCL13" --getis-star --output <dir>

# Bivariate Moran
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type bivariate_moran \
  --genes "EPCAM,VIM" --output <dir>

# Spatial graph topology summary
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type network_properties \
  --stats-n-neighs 6 --stats-n-rings 1 --output <dir>

# Cluster graph centrality
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type spatial_centrality \
  --centrality-score degree_centrality,closeness_centrality \
  --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Methodology

### Cluster-Level Methods

**Neighborhood enrichment**
- official engine: `squidpy.gr.nhood_enrichment()`
- consumes cluster labels plus a spatial graph
- key outputs: z-score matrix, neighbor-count matrix, strongest cluster pairs

**Ripley**
- official engine: `squidpy.gr.ripley()`
- consumes cluster labels plus coordinates
- key outputs: per-cluster distance curves and curve summary table

**Co-occurrence**
- official engine: `squidpy.gr.co_occurrence()`
- consumes cluster labels plus coordinates
- key outputs: distance-binned pairwise co-occurrence curves

### Gene-Level Methods

**Moran / Geary**
- official engine: `squidpy.gr.spatial_autocorr()`
- consume selected genes plus the spatial graph
- key outputs: ranked gene table with adjusted p-values and statistic-specific
  interpretations

**Local Moran**
- official engine: `esda.Moran_Local`
- consumes a single-gene vector plus PySAL weights derived from the spatial
  graph
- key outputs: per-gene hotspot summary and per-spot local scores

**Getis-Ord**
- official engine: `esda.G_Local`
- consumes a single-gene vector plus PySAL weights
- key outputs: hotspot / coldspot counts and per-spot Gi z-scores

**Bivariate Moran**
- official engine: `esda.Moran_BV`
- consumes exactly two genes plus PySAL weights
- key outputs: bivariate I, permutation p-value, and interpretation

### Network-Level Methods

**Network properties**
- graph summary with NetworkX on the Squidpy spatial graph
- key outputs: degree, clustering, density, connected-component summary

**Spatial centrality**
- official engine: `squidpy.gr.centrality_scores()`
- key outputs: per-cluster `degree_centrality`, `average_clustering`, and
  `closeness_centrality`

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── *.png
│   └── manifest.json
├── figure_data/
│   ├── analysis_summary.csv
│   ├── analysis_results.csv          # when a main result table exists
│   ├── top_results.csv               # when a top-table view exists
│   ├── pair_summary.csv              # cluster pair summaries when available
│   ├── cluster_summary.csv           # ripley-style summaries when available
│   ├── per_cluster_metrics.csv       # network / centrality summaries when available
│   ├── spot_statistics.csv           # local spot-level statistics when available
│   └── manifest.json
├── tables/
│   └── *.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── requirements.txt
    └── r_visualization.sh
```

The bundled repo-side R helpers live under:

```text
skills/spatial/spatial-statistics/r_visualization/
├── README.md
└── stats_publication_template.R
```

## Safety

- **Report the graph contract**: graph-based outputs are only interpretable if
  `stats_n_neighs`, `stats_n_rings`, and graph reuse/rebuild behavior are
  recorded.
- **Do not flatten evidence types**: cluster-level neighbor structure, gene
  autocorrelation, and graph topology answer different questions.
- **Require two genes for bivariate Moran**: do not silently improvise a gene
  pair.
- **Use method-correct language**: a local hotspot map is not a differential
  expression test, and centrality is not a cell-cell communication result.

## Integration With Orchestrator

**Trigger conditions**:

- spatial statistics
- Moran / Geary
- Ripley / co-occurrence
- hotspot / coldspot analysis
- spatial graph centrality

**Chaining**:

- often follows `spatial-preprocess`
- can refine genes selected from `spatial-genes` or markers selected from
  `spatial-de`

## Citations

- [Squidpy](https://squidpy.readthedocs.io/) — spatial graph and statistics
  toolkit
- [PySAL / esda](https://pysal.org/esda/) — local and bivariate spatial
  autocorrelation statistics
- [NetworkX](https://networkx.org/) — graph topology summary utilities
