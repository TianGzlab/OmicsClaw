---
doc_id: skill-guide-scatac-preprocessing
title: OmicsClaw Skill Guide — scATAC Preprocessing
doc_type: method-reference
domains: [singlecell]
related_skills: [scatac-preprocessing, scatac-preprocess]
search_terms: [scATAC preprocessing, TF-IDF, LSI, ATAC clustering, chromatin accessibility, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — scATAC Preprocessing

**Status**: implementation-aligned guide derived from the current OmicsClaw
`scatac-preprocessing` skill. This guide explains the real wrapper behavior,
public parameter semantics, and method-selection logic. It does not imply that
all fragment-aware or motif-aware scATAC workflows are already exposed.

## Purpose

Use this guide when you need to decide:

- whether the input is suitable for scATAC preprocessing right now
- how to explain the current TF-IDF + LSI workflow without overclaiming scope
- how to tune sparsity filters, retained peak budget, latent dimensions, and
  graph granularity

## Step 1: Inspect The Data First

Before running preprocessing, check:

- **Matrix state**:
  - the wrapper assumes `adata.X` is a raw-count-like or binary peak matrix
  - if the matrix already looks normalized, aggregated, gene-activity-based, or
    embedding-like, say that explicitly
- **Input format**:
  - current wrapper can load `.h5ad`, `.h5`, `.loom`, delimited matrices, and
    10x-style directories through the shared loader
- **Feature naming**:
  - peak IDs should be stable enough to interpret retained-peak summaries later
- **Sparsity**:
  - extremely sparse datasets are sensitive to `min_peaks`, `min_cells`, and
    `n_top_peaks`
- **Workflow scope**:
  - the current wrapper does not start from fragment files and does not perform
    motif or gene-activity inference

Important implementation notes in current OmicsClaw:

- Explicit method requests are validated and should not silently fall back.
- `min_peaks`, `min_cells`, and `n_top_peaks` are wrapper-level controls.
- The current wrapper computes a Signac-style TF-IDF transform, then runs
  truncated SVD / LSI, Scanpy neighbors, UMAP, and Leiden.
- The processed output retains the selected peak space used for LSI.

## Step 2: Choose The Method Deliberately

### `tfidf_lsi`

Best when:

- the user already has a peak-by-cell matrix
- the goal is standard scATAC latent embedding and clustering
- the environment should stay in a light Python-native path

Wrapper behavior:

- filters cells by detected peaks and peaks by cell support
- keeps the globally most accessible peaks up to `n_top_peaks`
- computes a Signac-style TF-IDF transform with `tfidf_scale_factor`
- runs truncated SVD / LSI
- builds Scanpy neighbors, UMAP, and Leiden from the latent representation

## Step 3: Tune Parameters In A Stable Order

### Shared sparsity filters

Tune in this order:

1. `min_peaks`
2. `min_cells`

Guidance:

- raise `min_peaks` when many very sparse barcodes look uninformative
- lower `min_peaks` cautiously when the dataset is genuinely shallow
- raise `min_cells` to suppress ultra-rare peaks before LSI
- lower `min_cells` cautiously when the study focuses on rare regulatory events

Important warning:

- these are wrapper-level sparsity gates and are not the same thing as every
  upstream toolkit's QC interface

### Retained peak budget

Tune in this order:

1. `n_top_peaks`

Guidance:

- start with the default when dataset size is modest
- increase it for larger or more heterogeneous datasets if the latent space
  looks oversimplified
- reduce it if runtime or memory pressure becomes significant

Important warning:

- current OmicsClaw keeps peaks by global accessibility rank after filtering

### TF-IDF and latent space

Tune in this order:

1. `tfidf_scale_factor`
2. `n_lsi`

Guidance:

- leave `tfidf_scale_factor` at the default unless there is a strong reason to
  harmonize with another local workflow
- start with `n_lsi=30`
- reduce `n_lsi` for smaller datasets
- increase `n_lsi` if the dataset is large and cluster separation remains coarse

Important warning:

- requested `n_lsi` and actually computed `n_lsi_used` may differ if the matrix
  becomes too small after filtering

### Graph and clustering

Tune in this order:

1. `n_neighbors`
2. `leiden_resolution`

Guidance:

- increase `n_neighbors` when you want smoother, broader neighborhoods
- decrease `n_neighbors` for more local structure
- increase `leiden_resolution` when clusters are too coarse
- lower `leiden_resolution` when clusters fragment too aggressively

## Step 4: Show An Effective Run Summary Before Execution

Before execution, summarize the real run in a compact block, for example:

```text
About to run scATAC preprocessing
  Method: tfidf_lsi
  Effective sparsity filters: min_peaks=200, min_cells=5
  Retained peaks: n_top_peaks=10000
  Latent space: tfidf_scale_factor=10000, n_lsi=30
  Graph: n_neighbors=15, leiden_resolution=0.8
  Note: current wrapper starts from a peak matrix, not fragments.
```

## Step 5: What To Say After The Run

- If too few cells remain: revisit `min_peaks` first.
- If too few peaks remain: revisit `min_cells`.
- If clusters are too coarse: revisit `n_lsi`, `n_neighbors`, and `leiden_resolution`.
- If runtime is too heavy: revisit `n_top_peaks`.
- If the input looked pre-transformed on entry: explicitly warn that raw-count
  preprocessing assumptions may have been violated.

## Step 6: Explain Outputs Correctly

When summarizing results:

- describe `processed.h5ad` as the downstream-ready AnnData in the retained peak space
- describe `figures/` as the standard Python gallery users should inspect first
- describe `figure_data/` as the plotting contract for future customization
- describe `tables/peak_summary.csv` as the retained-peak accessibility table
- describe `tables/lsi_variance_ratio.csv` as the compact latent-space summary
- describe `result.json.data.params` as the replayable public CLI parameters
- describe `result.json.data.effective_params` as the actual runtime
  configuration plus wrapper-fixed behavior
- describe `result.json.data.visualization` as the structured gallery contract

Do **not** say "fragment preprocessing completed", "motif analysis completed",
or "gene activity completed" unless a later scATAC skill actually ran.
