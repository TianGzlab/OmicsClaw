---
name: spatial-genes
description: >-
  Find genes with spatially variable expression patterns using Moran's I,
  SpatialDE, SPARK-X, or FlashS. Identifies genes whose expression is non-randomly
  distributed across tissue coordinates.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [spatial, SVG, spatially-variable-genes, morans, spatialde, sparkx, flashs]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--flashs-bandwidth"
    - "--flashs-n-rand-features"
    - "--fdr-threshold"
    - "--method"
    - "--morans-coord-type"
    - "--morans-corr-method"
    - "--morans-n-neighs"
    - "--morans-n-perms"
    - "--n-top-genes"
    - "--sparkx-max-genes"
    - "--sparkx-num-cores"
    - "--sparkx-option"
    - "--spatialde-aeh-lengthscale"
    - "--spatialde-aeh-patterns"
    - "--spatialde-min-counts"
    - "--spatialde-no-aeh"
    param_hints:
      morans:
        priority: "morans_coord_type → morans_n_neighs → morans_n_perms"
        params: ["morans_coord_type", "morans_n_neighs", "morans_n_perms", "morans_corr_method",
          "fdr_threshold", "n_top_genes"]
        defaults: {morans_coord_type: "auto", morans_n_neighs: 6, morans_n_perms: 100,
          morans_corr_method: "fdr_bh", fdr_threshold: 0.05, n_top_genes: 20}
        requires: ["obsm.spatial", "X_log_normalized"]
        tips:
        - "--morans-coord-type: `auto` lets Squidpy infer Visium grid vs generic coordinates."
        - "--morans-n-neighs: Main locality knob for generic coordinates."
        - "--morans-n-perms: Permutation depth; set 0 for analytic-only p-values."
        - "--morans-corr-method: Multiple-testing correction passed to Squidpy/statsmodels."
      spatialde:
        priority: "spatialde_no_aeh → spatialde_min_counts → spatialde_aeh_patterns/aeh_lengthscale"
        params: ["spatialde_no_aeh", "spatialde_min_counts", "spatialde_aeh_patterns",
          "spatialde_aeh_lengthscale", "fdr_threshold", "n_top_genes"]
        defaults: {spatialde_no_aeh: false, spatialde_min_counts: 3, fdr_threshold: 0.05,
          n_top_genes: 20}
        requires: ["obsm.spatial", "counts_or_raw"]
        tips:
        - "--spatialde-min-counts: Gene prefilter before Gaussian-process fitting."
        - "--spatialde-no-aeh: Skip the AEH pattern-grouping stage and only return
          per-gene SpatialDE statistics."
        - "--spatialde-aeh-patterns / --spatialde-aeh-lengthscale: Optional overrides
          for AEH pattern count `C` and lengthscale `l`."
      sparkx:
        priority: "sparkx_option → sparkx_num_cores → sparkx_max_genes"
        params: ["sparkx_option", "sparkx_num_cores", "sparkx_max_genes", "fdr_threshold",
          "n_top_genes"]
        defaults: {sparkx_option: "mixture", sparkx_num_cores: 1, sparkx_max_genes: 5000,
          fdr_threshold: 0.05, n_top_genes: 20}
        requires: ["obsm.spatial", "counts_or_raw", "Rscript"]
        tips:
        - "--sparkx-option: Passed through to `spark.sparkx`; the official SPARK-X
          example uses `mixture`."
        - "--sparkx-num-cores: Passed through as `numCores` in the R implementation."
        - "--sparkx-max-genes: OmicsClaw wrapper cap for very large matrices before
          calling SPARK-X."
      flashs:
        priority: "flashs_bandwidth → flashs_n_rand_features"
        params: ["flashs_bandwidth", "flashs_n_rand_features", "fdr_threshold", "n_top_genes"]
        defaults: {flashs_n_rand_features: 500, fdr_threshold: 0.05, n_top_genes: 20}
        requires: ["obsm.spatial", "counts_or_raw"]
        tips:
        - "--flashs-bandwidth: Wrapper-level override for the kernel bandwidth; default
          is estimated from coordinate spread."
        - "--flashs-n-rand-features: Wrapper-level sketch size controlling FlashS
          approximation fidelity vs runtime."
    legacy_aliases: [genes, spatial-svg-detection]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
      - python3
      env: []
      config: []
    emoji: "🧭"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
    - kind: pip
      package: scanpy
      bins: []
    - kind: pip
      package: squidpy
      bins: []
    trigger_keywords:
    - spatially variable gene
    - spatial gene
    - SVG
    - SpatialDE
    - SPARK-X
    - spatial pattern
    - Moran
    - spatial autocorrelation
    script: spatial_genes.py
---

# 🧭 Spatial Genes

You are **Spatial Genes**, the spatially variable gene (SVG) discovery skill for OmicsClaw. Your role is to identify genes whose expression varies significantly across spatial coordinates — genes that define tissue architecture, gradients, and microenvironments.

## Why This Exists

- **Without it**: Users manually run spatial autocorrelation tests with inconsistent parameters and ad-hoc filtering
- **With it**: One command computes Moran's I for all genes, ranks by spatial variability, and produces publication-ready scatter plots
- **Why OmicsClaw**: Standardised SVG detection ensures consistent methodology, method-specific tuning hints, structured outputs, and wrapper-generated guides across spatial analysis pipelines

## Core Capabilities

1. **Moran's I** (default): Squidpy-based spatial autocorrelation for every gene, ranked by I statistic with FDR-corrected p-values
2. **SpatialDE**: Gaussian process regression via SpatialDE (identifies smooth spatial patterns)
3. **SPARK-X**: Non-parametric kernel test via SPARK-X in R (requires R installation)
4. **FlashS**: Randomized kernel approximation (Python native, fast on large datasets)
5. **Standard Python gallery**: recipe-driven overview, diagnostic, supporting, and uncertainty figures under `figures/`
6. **Structured figure-data contract**: `figure_data/` exports ranked genes, significant SVGs, observation-level metric tables, point tables, and a manifest for downstream plotting
7. **Persisted gallery annotations**: top-SVG mean expression, max expression, detected-count, and dominant-gene columns are written back to `adata.obs` for stable downstream reuse
8. **Optional R visualization layer**: bundled `r_visualization/` templates consume `figure_data/` without recomputing science
9. **Ranked table exports**: CSVs for all tested genes, top SVGs, significant SVGs, and observation metrics

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (normalised), `layers["counts"]` (raw), `obsm["spatial"]` | `processed.h5ad` |
| Demo | n/a | `--demo` flag | Runs spatial-preprocess demo first |

### Input Matrix Convention

Different SVG methods have different statistical assumptions. The skill automatically selects the correct input matrix per method:

| Method | Input Matrix | Rationale |
|--------|-------------|-----------|
| `morans` | `adata.X` (log-normalized) | Squidpy `spatial_autocorr` computes autocorrelation on continuous expression values; not a count-distribution model |
| `spatialde` | `adata.layers["counts"]` (raw) | NaiveDE.stabilize() applies its own variance-stabilizing transform; feeding already-normalized data breaks assumptions |
| `sparkx` | `adata.layers["counts"]` (raw) | SPARK-X directly inputs the raw count matrix for kernel-based testing |
| `flashs` | `adata.layers["counts"]` (raw) | FlashS exploits sparsity and count structure (binary presence + rank + count) |

**Data layout requirement**: Preprocessing must store raw counts before normalization:

```python
adata.layers["counts"] = adata.X.copy()   # before normalize_total + log1p
adata.X = lognorm_expr                     # after normalize_total + log1p
```

If `layers["counts"]` is missing, the skill will fall back to `adata.raw` (if available) or `adata.X` with a warning.

## Workflow

1. **Load**: Read preprocessed h5ad and verify spatial coordinates exist.
2. **Validate**: Select the required expression representation and method-specific tuning flags.
3. **Run SVG method**: Execute Moran's I, SpatialDE, SPARK-X, or FlashS.
4. **Filter & rank**: Apply the method-appropriate adjusted significance metric and rank genes by method-specific score.
5. **Render the standard gallery**: build the OmicsClaw narrative gallery with overview, diagnostic, supporting, and uncertainty panels.
6. **Export figure-ready data**: write `figure_data/*.csv` and `figure_data/manifest.json` for downstream customization.
7. **Report and export**: write `report.md`, `result.json`, `processed.h5ad`, tables, and the reproducibility bundle including optional R visualization entrypoints.

## Visualization Contract

OmicsClaw treats `spatial-genes` visualization as a two-layer system:

1. **Python standard gallery**: the canonical result layer. This is the default output users should inspect first.
2. **R customization layer**: an optional styling and publication layer that reads `figure_data/` and does not recompute SVG statistics.

The standard gallery is declared as a recipe instead of hard-coded `if/else`
plot calls. Current gallery roles include:

- `overview`: top SVG feature maps on tissue coordinates and UMAP
- `diagnostic`: method score vs significance, plus Moran ranking when available
- `supporting`: top-gene score summary panel plus observation-level SVG burden context from persisted gallery metrics
- `uncertainty`: significance distribution across tested genes

This separation keeps the OmicsClaw output stable while still allowing later
R-side beautification and method-specific extensions.

## CLI Reference

```bash
# Standard usage (Moran's I, default)
oc run spatial-genes \
  --input <processed.h5ad> --output <report_dir>

# Moran's I tuning
oc run spatial-genes \
  --input <processed.h5ad> --method morans \
  --morans-coord-type auto --morans-n-neighs 8 --morans-n-perms 500 \
  --morans-corr-method fdr_bh --n-top-genes 30 --fdr-threshold 0.01 --output <dir>

# SpatialDE + AEH pattern grouping
oc run spatial-genes \
  --input <processed.h5ad> --method spatialde \
  --spatialde-min-counts 5 --spatialde-aeh-patterns 6 --output <dir>

# SPARK-X method (requires R + SPARK package)
oc run spatial-genes \
  --input <processed.h5ad> --method sparkx \
  --sparkx-option mixture --sparkx-num-cores 4 --sparkx-max-genes 3000 --output <dir>

# FlashS method (fast on large data)
oc run spatial-genes \
  --input <processed.h5ad> --method flashs \
  --flashs-n-rand-features 1000 --flashs-bandwidth 50.0 --output <dir>

# Demo mode
oc run spatial-genes --demo --output /tmp/svg_demo

# Direct script entrypoint
python skills/spatial/spatial-genes/spatial_genes.py \
  --input <processed.h5ad> --method morans --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Find spatially variable genes in my data using Moran's I"
- "Use SpatialDE to detect genes with spatial patterns"

## Algorithm / Methodology

### Moran's I (default)

1. **Input**: `adata.X` (log-normalized expression)
2. **Spatial graph**: `squidpy.gr.spatial_neighbors(...)` builds a spatial graph from `obsm["spatial"]`; OmicsClaw can now pass `coord_type` through instead of always forcing `generic`
3. **Autocorrelation**: `squidpy.gr.spatial_autocorr(adata, mode="moran", n_perms=..., corr_method=..., n_jobs=1)` computes Moran's I for every gene
4. **Moran's I range**: -1 (perfect dispersion) to +1 (perfect clustering); 0 = random
5. **Filtering**: Retain genes with `Moran's I > 0` and the corrected significance column from `corr_method` (for example `pval_norm_fdr_bh`) below `fdr_threshold`; if Squidpy does not expose a corrected column, OmicsClaw falls back to raw `pval_norm`
6. **Ranking**: Sort by descending Moran's I statistic

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `morans` | `morans`, `spatialde`, `sparkx`, or `flashs` |
| `--n-top-genes` | `20` | Number of top SVGs to report |
| `--fdr-threshold` | `0.05` | FDR-corrected p-value cutoff |
| `--morans-coord-type` | `auto` | Neighbor-graph layout hint: `auto`, `generic`, or `grid` |
| `--morans-n-neighs` | `6` | Number of spatial neighbors for generic coordinates |
| `--morans-n-perms` | `100` | Number of permutations for empirical p-values; `0` disables permutations |
| `--morans-corr-method` | `fdr_bh` | Multiple-testing correction method |

### SpatialDE

1. **Input**: `adata.layers["counts"]` (raw counts)
2. **Dependency**: Requires `SpatialDE` + `NaiveDE` packages
3. **Preprocessing**: NaiveDE.stabilize() applies variance-stabilizing transform on raw counts, then regresses out total counts
4. **Test**: Gaussian process regression comparing spatially-aware vs spatially-unaware models
5. **Optional AEH**: OmicsClaw can optionally run `SpatialDE.spatial_patterns()` to group significant genes into AEH patterns using pattern count `C` and lengthscale `l`
6. **Output**: Genes ranked by likelihood ratio statistic, with significance taken from SpatialDE `qval`

**Core tuning flags**:
- `--spatialde-min-counts`: Per-gene count filter before SpatialDE fitting.
- `--spatialde-no-aeh`: Skip AEH pattern grouping and only report per-gene SpatialDE statistics.
- `--spatialde-aeh-patterns`: Override AEH pattern count `C`.
- `--spatialde-aeh-lengthscale`: Override AEH lengthscale `l`.

### SPARK-X

1. **Input**: `adata.layers["counts"]` (raw counts)
2. **Dependency**: Requires R + SPARK R package
3. **Test**: Non-parametric kernel-based test directly on count matrix via `spark.sparkx(counts, coords, numCores=..., option=...)`
4. **Advantage**: Robust to non-linear spatial patterns, with significance taken from the SPARK-X adjusted p-value column when available

**Core tuning flags**:
- `--sparkx-option`: Passed through to the R implementation; the official example uses `mixture`.
- `--sparkx-num-cores`: Passed through as `numCores`.
- `--sparkx-max-genes`: OmicsClaw wrapper cap for very large matrices before the R call.

### FlashS

1. **Input**: `adata.layers["counts"]` (raw counts)
2. **Dependency**: Python native (no R required)
3. **Method**: OmicsClaw uses a randomized-kernel / random-feature approximation inspired by FlashS's frequency-domain, multi-scale kernel design
4. **Advantage**: Fast on large datasets (>10k spots), with OmicsClaw reporting Benjamini-Hochberg `qval` alongside the wrapper score

**Core tuning flags**:
- `--flashs-n-rand-features`: Wrapper sketch size controlling approximation fidelity vs runtime.
- `--flashs-bandwidth`: Wrapper kernel bandwidth override; omitted means data-adaptive estimation.

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── top_svg_spatial.png
│   ├── top_svg_umap.png
│   ├── top_svg_scores.png
│   ├── svg_score_vs_significance.png
│   ├── svg_significance_distribution.png
│   ├── moran_ranking.png              # Moran's I only
│   └── manifest.json
├── figure_data/
│   ├── svg_results.csv
│   ├── top_svg_scores.csv
│   ├── significant_svgs.csv
│   ├── svg_observation_metrics.csv
│   ├── top_svg_spatial_points.csv
│   ├── top_svg_umap_points.csv       # if X_umap is available
│   ├── svg_run_summary.csv
│   └── manifest.json
├── tables/
│   ├── svg_results.csv
│   ├── top_svg_scores.csv
│   ├── significant_svgs.csv
│   └── svg_observation_metrics.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── requirements.txt
    └── r_visualization.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution usually produces the
skill-native outputs plus `reproducibility/commands.sh`.

The bundled repo-side R helpers live under:

```text
skills/spatial/spatial-genes/r_visualization/
├── README.md
└── svg_publication_template.R
```

## Dependencies

**Required (Python)**:
- `scanpy` >= 1.9 — single-cell/spatial analysis
- `squidpy` >= 1.2 — spatial autocorrelation and neighbor graphs
- `matplotlib` — plotting
- `numpy`, `pandas` — numerics

**Optional (Python)**:
- `SpatialDE` & `NaiveDE` — Gaussian process-based SVG detection
- `flashs` — FlashS randomized kernel approximation
- `statsmodels` — multiple-testing correction used by some backends and wrappers

**Optional (R Environment / Subprocess)**:
- R system installation
- `SPARK` (R package) — SPARK-X kernel test

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Reports follow the standard OmicsClaw reporting and disclaimer convention.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.
- **Stable persistence**: SVG results and gallery metadata are stored in `adata.uns`, while observation-level SVG summary columns are persisted in `adata.obs`.
- **Non-destructive**: original expression matrices are preserved.

## Integration with Orchestrator

**Trigger conditions**: 
- Automatically invoked dynamically based on tool metadata and user intent matching.
- Keywords — spatially variable gene, spatial gene, SVG, SpatialDE, SPARK-X, spatial pattern, Moran

**Chaining partners**:
- `spatial-preprocess`: Provides the preprocessed h5ad input
- `spatial-domains`: SVGs often overlap with domain-defining genes
- `spatial-de`: Compare SVGs with cluster-based DE results

## Citations

- [Squidpy](https://squidpy.readthedocs.io/) — spatial autocorrelation (Moran's I)
- [SpatialDE](https://doi.org/10.1038/nmeth.4636) — Svensson et al., *Nature Methods* 2018
- [SPARK-X](https://doi.org/10.1186/s13059-021-02404-0) — Zhu et al., *Genome Biology* 2021
- [FlashS](https://github.com/cafferychen777/FlashS) — frequency-domain kernel testing for SVGs
- [Moran's I](https://en.wikipedia.org/wiki/Moran%27s_I) — spatial autocorrelation statistic
