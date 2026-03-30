---
name: sc-preprocessing
description: >-
  Single-cell RNA-seq preprocessing with Scanpy, Seurat LogNormalize, or
  Seurat SCTransform workflows. Performs QC filtering, normalization, highly
  variable gene selection, PCA, neighborhood graph construction, UMAP, and
  clustering, then exports a downstream-ready AnnData plus a standard
  OmicsClaw gallery and reproducibility bundle.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, preprocessing, qc, normalization, clustering]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--leiden-resolution"
      - "--max-mt-pct"
      - "--method"
      - "--min-cells"
      - "--min-genes"
      - "--n-neighbors"
      - "--n-pcs"
      - "--n-top-hvg"
    param_hints:
      scanpy:
        priority: "min_genes/max_mt_pct → n_top_hvg → n_pcs/n_neighbors → leiden_resolution"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs", "n_neighbors", "leiden_resolution"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000, n_pcs: 50, n_neighbors: 15, leiden_resolution: 1.0}
        requires: ["count_like_matrix_in_X", "scanpy", "igraph", "leidenalg"]
        tips:
          - "--method scanpy: Python-native path using `scanpy.pp.highly_variable_genes(..., flavor='seurat')`, PCA on HVGs, Scanpy neighbors, UMAP, and Leiden."
          - "--max-mt-pct: Wrapper-level filtering threshold applied after QC metric calculation and before normalization."
          - "--n-neighbors / --leiden-resolution: Main graph-granularity controls; current OmicsClaw defaults match the Scanpy path, not Seurat's upstream defaults."
      seurat:
        priority: "min_genes/max_mt_pct → n_top_hvg → n_pcs/n_neighbors → leiden_resolution"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs", "n_neighbors", "leiden_resolution"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000, n_pcs: 50, n_neighbors: 20, leiden_resolution: 0.8}
        requires: ["Rscript", "Seurat", "SingleCellExperiment", "zellkonverter"]
        tips:
          - "--method seurat: R-backed `CreateSeuratObject → NormalizeData(LogNormalize) → FindVariableFeatures(vst) → ScaleData → RunPCA → FindNeighbors → FindClusters → RunUMAP`."
          - "--n-top-hvg: Mapped to Seurat `FindVariableFeatures(..., nfeatures=...)`."
          - "--n-neighbors / --leiden-resolution: Mapped to Seurat `FindNeighbors(k.param=...)` and `FindClusters(resolution=...)`, while OmicsClaw standardizes the output cluster column to `leiden`."
      sctransform:
        priority: "max_mt_pct → n_top_hvg → n_pcs/n_neighbors → leiden_resolution"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs", "n_neighbors", "leiden_resolution"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 3000, n_pcs: 50, n_neighbors: 20, leiden_resolution: 0.8}
        requires: ["Rscript", "Seurat", "SingleCellExperiment", "zellkonverter", "sctransform"]
        tips:
          - "--method sctransform: R-backed `SCTransform(variable.features.n=...)` path followed by PCA, neighbor graph construction, clustering, and UMAP in Seurat."
          - "--n-top-hvg: Mapped to `SCTransform(variable.features.n=...)`; current OmicsClaw default follows the upstream SCTransform-style 3000-feature regime."
          - "--max-mt-pct: Still applied as wrapper-level QC filtering before SCTransform, not inside SCTransform itself."
    legacy_aliases: [sc-preprocess]
    saves_h5ad: true
    requires_preprocessed: false
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧫"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - single cell preprocess
      - scRNA preprocessing
      - QC filter normalize
      - clustering UMAP PCA
      - Seurat preprocessing
      - SCTransform preprocessing
---

# 🧫 Single-Cell Preprocessing

You are **SC Preprocessing**, the OmicsClaw skill for turning raw-count-like
single-cell RNA-seq input into a downstream-ready AnnData with QC-filtered
cells, normalized expression, highly variable gene annotations, embedding,
graph structure, clustering, and a standard result gallery.

## Why This Exists

- **Without it**: users manually stitch together QC, normalization, HVG selection, PCA, graph construction, UMAP, and clustering with inconsistent defaults
- **With it**: one command produces a stable preprocessing object plus a standard OmicsClaw report, gallery, tables, and reproducibility bundle
- **Why OmicsClaw**: the wrapper keeps a common output contract across Python and R-backed preprocessing branches while exposing only a compact set of high-value controls

## Scope Boundary

Current OmicsClaw `sc-preprocessing` exposes **three implemented workflows**:

1. `scanpy`
2. `seurat`
3. `sctransform`

This skill does:

1. QC metric calculation
2. cell and gene filtering
3. normalization / transformation
4. highly variable gene selection
5. PCA, neighborhood graph, UMAP, and clustering
6. downstream-ready AnnData export

This skill does **not**:

1. ambient RNA correction
2. doublet detection
3. batch integration
4. annotation
5. differential expression

Those belong to later OmicsClaw skills.

## Core Capabilities

1. **Three preprocessing backends**: Scanpy, Seurat LogNormalize, and Seurat SCTransform
2. **Unified public controls**: one compact parameter set drives all backends while preserving method-aware defaults
3. **Stable gallery contract**: UMAP clusters, QC violin, HVG plot, and PCA variance figures under `figures/`
4. **Structured figure-data layer**: `figure_data/` exports summary, cluster, HVG, PCA, UMAP, and QC tables for downstream customization
5. **Downstream-ready AnnData**: processed matrix, counts layer, raw snapshot, HVG annotations, embeddings, graph, and cluster labels
6. **Notebook-first reproducibility**: README, report, result JSON, replay command, pinned requirements, and analysis notebook

## Input Formats

The current wrapper uses `skills.singlecell._lib.io.smart_load(...)`.

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | preferred path |
| 10x HDF5 | `.h5` | yes | delegated to the shared single-cell loader |
| Loom | `.loom` | yes | delegated to the shared single-cell loader |
| Delimited matrix | `.csv`, `.tsv` | yes | interpreted via the shared count-matrix loader |
| 10x directory | directory | yes | delegated to the shared 10x importer |
| Demo | `--demo` | yes | PBMC3k local/example fallback |

### Input Expectations

- The most reliable input is a **raw-count-like matrix in `adata.X`**.
- If `layers["counts"]` or `adata.raw` already exists, the wrapper will still
  export a standardized `processed.h5ad`, but preprocessing assumptions should
  be checked before rerunning on already-normalized data.
- For best scientific behavior, do **not** feed scaled, regressed, or fully
  processed matrices into this skill.

## Workflow

1. **Load**: read input via the shared single-cell loader or demo data.
2. **Validate method**: confirm the requested backend is actually available; explicit method requests are not silently rewritten.
3. **QC and filtering**:
   - filter cells by `min_genes`
   - filter genes by `min_cells`
   - compute mitochondrial QC and filter by `max_mt_pct`
4. **Branch by backend**:
   - `scanpy`: `normalize_total → log1p → highly_variable_genes(flavor='seurat') → scale → PCA → neighbors → UMAP → Leiden`
   - `seurat`: `CreateSeuratObject → NormalizeData(LogNormalize) → FindVariableFeatures(vst) → ScaleData → RunPCA → FindNeighbors → FindClusters → RunUMAP`
   - `sctransform`: `CreateSeuratObject → SCTransform → RunPCA → FindNeighbors → FindClusters → RunUMAP`
5. **Write standard outputs**: `processed.h5ad`, report, result JSON, gallery, figure-data CSVs, summary tables, README, and notebook.

## CLI Reference

```bash
# Default Scanpy path
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input <raw_sc.h5ad> --output <dir>

# Explicit Seurat path
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input <raw_sc.h5ad> --method seurat --output <dir>

# Explicit SCTransform path
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input <raw_sc.h5ad> --method sctransform --output <dir>

# Tune graph granularity
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input <raw_sc.h5ad> --method scanpy \
  --n-top-hvg 3000 --n-pcs 50 --n-neighbors 20 --leiden-resolution 0.8 \
  --output <dir>

# Demo
oc run sc-preprocessing --demo --output /tmp/sc_preprocess_demo
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | preprocessing backend | `scanpy`, `seurat`, or `sctransform` |
| `--min-genes` | cell filtering threshold | filters low-complexity cells |
| `--min-cells` | gene filtering threshold | filters rarely detected genes |
| `--max-mt-pct` | mitochondrial QC threshold | wrapper-level filter before downstream modeling |
| `--n-top-hvg` | HVG budget | maps to backend-specific HVG control |
| `--n-pcs` | PCA dimensionality | requested principal components |
| `--n-neighbors` | graph locality | Scanpy `n_neighbors` or Seurat `k.param` |
| `--leiden-resolution` | clustering granularity | Scanpy Leiden or Seurat `FindClusters(resolution=...)` |

### Parameter Design Notes

- The public flags are shared because they influence all three backends in the
  same semantic direction.
- Some backend-specific behavior is fixed in the wrapper and reported honestly
  in `effective_params`, for example:
  - Scanpy HVG flavor = `seurat`
  - Scanpy normalization target sum = `10000`
  - Scanpy scaling max value = `10`
  - Seurat normalization method = `LogNormalize`
  - Seurat variable feature method = `vst`
  - SCTransform regression of `%MT` when available
- These fixed choices are **wrapper-level implementation details**, not public
  knobs in the current skill contract.

## Algorithm / Methodology

### Common QC Contract

All three methods share the same high-level preprocessing structure:

1. start from count-like input
2. filter cells with `min_genes`
3. filter genes with `min_cells`
4. calculate mitochondrial percentage and filter with `max_mt_pct`
5. compute PCA, graph, UMAP, and clustering
6. export a standardized AnnData plus OmicsClaw gallery and tables

### `scanpy`

Current OmicsClaw `scanpy` preprocessing does:

1. `scanpy.pp.filter_cells(min_genes=...)`
2. `scanpy.pp.filter_genes(min_cells=...)`
3. mitochondrial tagging by prefix auto-detection (`MT-` or `mt-`)
4. `scanpy.pp.calculate_qc_metrics(...)`
5. `scanpy.pp.normalize_total(target_sum=10000)`
6. `scanpy.pp.log1p(...)`
7. `scanpy.pp.highly_variable_genes(..., flavor='seurat', n_top_genes=...)`
8. scaling with max value `10`
9. PCA on highly variable genes
10. neighbor graph, UMAP, and Leiden clustering

Important implementation note:

- The current Scanpy branch uses `flavor='seurat'`, not `seurat_v3`.
- This means the scanpy path expects normalized/log-transformed expression for
  HVG selection rather than raw-count HVG modeling.

### `seurat`

Current OmicsClaw `seurat` preprocessing calls the shared R script and runs:

1. `CreateSeuratObject(min.cells=..., min.features=...)`
2. `PercentageFeatureSet(pattern='^MT-' or '^mt-')`
3. filtering by `nFeature_RNA >= min_genes` and `percent.mt <= max_mt_pct`
4. `NormalizeData(...)` with Seurat's `LogNormalize` pathway
5. `FindVariableFeatures(selection.method='vst', nfeatures=...)`
6. `ScaleData(...)`
7. `RunPCA(npcs=...)`
8. `FindNeighbors(k.param=...)`
9. `FindClusters(resolution=...)`
10. `RunUMAP(dims=1:effective_pcs)`

Important implementation note:

- OmicsClaw reconstructs a standard AnnData output after the R run and
  standardizes the main cluster column to `leiden` for downstream compatibility.

### `sctransform`

Current OmicsClaw `sctransform` preprocessing runs the same R wrapper but
switches the normalization / feature-selection stage to:

1. `SCTransform(variable.features.n=..., vars.to.regress='percent.mt' when available)`
2. followed by `RunPCA`, `FindNeighbors`, `FindClusters`, and `RunUMAP`

Important implementation notes:

- `n_top_hvg` maps to `variable.features.n`.
- Current OmicsClaw does **not** expose additional SCTransform knobs such as
  `vst.flavor` or residual clipping; those remain fixed wrapper behavior.

## Stable Output Contract

### Files

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── umap_leiden.png
│   ├── qc_violin.png
│   ├── highly_variable_genes.png
│   ├── pca_variance.png
│   └── manifest.json
├── figure_data/
│   ├── manifest.json
│   ├── preprocess_summary.csv
│   ├── cluster_summary.csv
│   ├── hvg_summary.csv
│   ├── pca_variance_ratio.csv
│   ├── umap_points.csv
│   └── qc_metrics_per_cell.csv
├── tables/
│   ├── preprocess_summary.csv
│   ├── cluster_summary.csv
│   ├── hvg_summary.csv
│   ├── pca_variance_ratio.csv
│   └── qc_metrics_per_cell.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── analysis_notebook.ipynb
```

### Guaranteed AnnData Fields After Success

Current successful runs are expected to provide:

```text
adata.layers["counts"]
adata.raw
adata.var["highly_variable"]
adata.obsm["X_pca"]
adata.obsm["X_umap"]
adata.uns["neighbors"]
adata.obsp["connectivities"]
adata.obsp["distances"]
adata.obs["leiden"]
adata.obs["n_genes_by_counts"]
adata.obs["total_counts"]
adata.obs["pct_counts_mt"]
adata.uns["omicsclaw_analyses"]
```

R-backed methods additionally may provide:

```text
adata.obs["seurat_clusters"]
adata.uns["seurat_info"]
```

### Structured Result Contract

`result.json` includes:

- `summary.method`
- `summary.n_cells`, `summary.n_genes`, `summary.n_hvg`, `summary.n_clusters`
- `summary.n_pcs_used`
- `data.params` for replayable public CLI parameters
- `data.effective_params` for actual runtime configuration and resolved wrapper behavior
- `data.visualization.recipe_id = "standard-sc-preprocessing-gallery"`
- `data.visualization.available_figure_data`

### What Users Should Inspect First

1. `report.md`
2. `figures/umap_leiden.png`
3. `tables/preprocess_summary.csv`
4. `tables/cluster_summary.csv`
5. `processed.h5ad`

## Visualization Contract

`sc-preprocessing` treats Python output as the standard analysis gallery. The
current roles are:

- `overview`: UMAP clusters
- `diagnostic`: QC violin and HVG plot
- `supporting`: PCA variance

`figure_data/` is the stable plotting hand-off layer for future custom
visualization, including optional R-side styling without rerunning preprocessing.

## Practical Interpretation Notes

- If very few cells remain after preprocessing, revisit `min_genes` and
  `max_mt_pct` first.
- If clusters are too coarse, inspect `n_neighbors` and `leiden_resolution`.
- If clusters are overly fragmented, reduce `leiden_resolution` or increase
  `n_neighbors`.
- If HVGs look too narrow for a heterogeneous dataset, increase `n_top_hvg`.
- If the input already appears normalized or scaled, state that preprocessing
  assumptions may be violated before trusting the result.

## Example Queries

- "Preprocess this scRNA-seq dataset with Scanpy"
- "Run Seurat LogNormalize preprocessing and give me a processed h5ad"
- "Use SCTransform for preprocessing and clustering"
- "Filter by mitochondrial percentage, run PCA/UMAP, and cluster the cells"

## Dependencies

Core Python path:

- `scanpy`
- `igraph`
- `leidenalg`

R-backed paths additionally require:

- `Rscript`
- `Seurat`
- `SingleCellExperiment`
- `zellkonverter`
- `sctransform` for the `sctransform` method

## Safety And Guardrails

- This skill assumes **raw-count-like** input.
- Explicit method requests should fail clearly if the backend is unavailable;
  they should not silently switch to another scientific method.
- `max_mt_pct` is a wrapper-level QC filter and should be explained before the run.
- For short execution guardrails, see
  `knowledge_base/knowhows/KH-sc-preprocessing-guardrails.md`.
- For longer method and tuning guidance, see
  `knowledge_base/skill-guides/singlecell/sc-preprocessing.md`.
