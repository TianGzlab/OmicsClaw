---
doc_id: skill-guide-sc-preprocessing
title: OmicsClaw Skill Guide — SC Preprocessing
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-preprocessing, sc-preprocess]
search_terms: [single-cell preprocessing, Scanpy preprocessing, Seurat preprocessing, SCTransform, QC filtering, HVG, PCA, UMAP, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Preprocessing

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-preprocessing` skill. This guide explains the real wrapper behavior, public
parameter semantics, and method-selection logic. It is not a claim that all
single-cell preprocessing variations are already exposed in OmicsClaw.

## Purpose

Use this guide when you need to decide:

- whether the input is suitable for preprocessing right now
- which of `scanpy`, `seurat`, or `sctransform` fits the user's goal
- how to explain and tune QC, HVG, PCA, graph, and clustering settings without
  overclaiming what the wrapper does

## Step 1: Inspect The Data First

Before running preprocessing, check:

- **Matrix state**:
  - the wrapper assumes `adata.X` is still raw-count-like
  - if the matrix already looks normalized, logged, or scaled, say that explicitly
- **Input format**:
  - current wrapper can load `.h5ad`, `.h5`, `.loom`, delimited matrices, and 10x-style directories through the shared loader
- **Count preservation**:
  - if counts already exist in `layers["counts"]` or `adata.raw`, note that, but do not assume the whole object is already preprocessing-ready
- **Gene naming**:
  - mitochondrial tagging depends on `MT-` or `mt-` prefix detection
- **Dataset size and heterogeneity**:
  - this strongly affects `n_top_hvg`, `n_pcs`, `n_neighbors`, and clustering resolution
- **Backend availability**:
  - if the user explicitly wants `seurat` or `sctransform`, confirm the R stack is actually available before promising that method

Important implementation notes in current OmicsClaw:

- Explicit method requests are validated and should not silently fall back to another backend.
- `min_genes`, `min_cells`, and `max_mt_pct` are shared wrapper-level controls.
- The Scanpy branch currently uses `scanpy.pp.highly_variable_genes(..., flavor='seurat')`.
- The Seurat branch currently uses `NormalizeData(LogNormalize)` and `FindVariableFeatures(selection.method='vst')`.
- The SCTransform branch currently maps `n_top_hvg` to `SCTransform(variable.features.n=...)`.

## Step 2: Choose The Method Deliberately

### `scanpy`

Best when:

- the user wants a pure Python workflow
- the environment should stay fully local in Python
- the user wants the most transparent OmicsClaw-native path

Wrapper behavior:

- uses `normalize_total(target_sum=10000)`
- uses `log1p`
- uses HVG flavor `seurat`
- scales data and runs PCA, neighbors, UMAP, and Leiden in Scanpy

### `seurat`

Best when:

- the user explicitly wants the classic Seurat LogNormalize workflow
- the team expects Seurat-style feature selection and clustering behavior
- the required R packages are available

Wrapper behavior:

- creates a Seurat object from count-like data
- computes `percent.mt`
- filters by `min_genes` and `max_mt_pct`
- runs `NormalizeData`, `FindVariableFeatures(vst)`, `ScaleData`, `RunPCA`,
  `FindNeighbors`, `FindClusters`, and `RunUMAP`
- reimports results into a standardized AnnData

### `sctransform`

Best when:

- technical variation or sequencing-depth effects are strong
- the user explicitly wants Seurat SCTransform normalization
- the environment has the `sctransform` package available

Wrapper behavior:

- applies the same wrapper QC filtering first
- runs `SCTransform(variable.features.n=...)`
- regresses `percent.mt` when it is present
- then runs PCA, neighbors, clustering, and UMAP in Seurat

## Step 3: Tune Parameters In A Stable Order

### Shared QC filters

Tune in this order:

1. `min_genes`
2. `max_mt_pct`
3. `min_cells`

Guidance:

- raise `min_genes` when low-complexity cells dominate
- lower `min_genes` cautiously when the dataset is genuinely sparse
- lower `max_mt_pct` when poor-quality stressed cells dominate
- raise `max_mt_pct` cautiously for tissues where higher mitochondrial load may be biological
- use `min_cells` to remove ultra-rare genes before downstream structure learning

Important warning:

- these are wrapper-level QC gates shared across all three backends

### HVG budget

Tune in this order:

1. `n_top_hvg`

Guidance:

- start around 2000 for `scanpy` and `seurat`
- start around 3000 for `sctransform` if the user has not specified a value
- increase for larger or more heterogeneous datasets
- reduce for small or noisy datasets if the graph is becoming unstable

Important warning:

- the biological effect of `n_top_hvg` depends on the backend-specific feature-selection procedure

### PCA and graph

Tune in this order:

1. `n_pcs`
2. `n_neighbors`

Guidance:

- start with `n_pcs=50`
- use fewer PCs when the dataset is small or simple
- use larger `n_neighbors` when you want broader, smoother neighborhoods
- use smaller `n_neighbors` when you want more local structure

Important warning:

- requested PCs and actually computed PCs are not always identical; inspect the recorded `n_pcs_used`

### Clustering

Tune in this order:

1. `leiden_resolution`

Guidance:

- increase it when clusters are too coarse
- lower it when clusters are fragmented

Important warning:

- for R-backed methods this parameter still maps to Seurat `FindClusters(resolution=...)`, even though OmicsClaw standardizes the output cluster column to `leiden`

## Step 4: Show An Effective Run Summary Before Execution

Before execution, summarize the real run in a compact block, for example:

```text
About to run single-cell preprocessing
  Method: sctransform
  Effective QC: min_genes=200, min_cells=3, max_mt_pct=20
  Feature selection: n_top_hvg=3000
  Graph: n_pcs=50, n_neighbors=20, leiden_resolution=0.8
  Note: QC thresholds are wrapper-level filters applied before the SCTransform stage.
```

This matters because users often confuse wrapper QC filters with backend-native defaults.

## Step 5: What To Say After The Run

- If too few cells remain: revisit `min_genes` and `max_mt_pct` first.
- If clusters are too coarse: revisit `n_neighbors` and `leiden_resolution`.
- If clusters are too fragmented: lower `leiden_resolution` or increase `n_neighbors`.
- If HVGs seem too restrictive: revisit `n_top_hvg`.
- If the input looked already normalized on entry: explicitly warn that preprocessing assumptions may have been violated.

## Step 6: Explain Outputs Correctly

When summarizing results:

- describe `processed.h5ad` as the downstream-ready AnnData
- describe `figures/` as the standard Python gallery users should inspect first
- describe `figure_data/` as the plotting contract for future custom or R-side visualization
- describe `tables/preprocess_summary.csv` as the compact run summary
- describe `tables/cluster_summary.csv` as the primary cluster-size table
- describe `result.json.data.params` as the replayable public CLI parameters
- describe `result.json.data.effective_params` as the actual runtime configuration and fixed wrapper behavior
- describe `result.json.data.visualization` as the structured gallery contract

Do **not** say "Seurat preprocessing completed" or "Scanpy preprocessing
completed" without also surfacing the effective QC and graph settings that
actually governed the run.
