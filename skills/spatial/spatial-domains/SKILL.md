---
name: spatial-domains
description: >-
  Identify tissue regions and spatial niches from preprocessed spatial transcriptomics
  data using Leiden, Louvain, SpaGCN, STAGATE, GraphST, or BANKSY.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [spatial, domains, niche, tissue-region, clustering, leiden, louvain, spagcn, stagate, graphst, banksy, cellcharter]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--auto-k"
      - "--auto-k-min"
      - "--auto-k-max"
      - "--dim-output"
      - "--epochs"
      - "--k-nn"
      - "--lambda-param"
      - "--method"
      - "--n-domains"
      - "--n-layers"
      - "--num-neighbours"
      - "--pre-resolution"
      - "--rad-cutoff"
      - "--refine"
      - "--resolution"
      - "--spagcn-p"
      - "--spatial-weight"
      - "--stagate-alpha"
      - "--use-rep"
    param_hints:
      leiden:
        priority: "resolution → spatial_weight"
        params: ["resolution", "spatial_weight"]
        defaults: {resolution: 1.0, spatial_weight: 0.3}
        requires: ["obsm.spatial"]
        tips:
          - "--resolution: Clustering granularity (default 1.0)."
          - "--spatial-weight: Spatial graph influence (default 0.3)."
      louvain:
        priority: "resolution → spatial_weight"
        params: ["resolution", "spatial_weight"]
        defaults: {resolution: 1.0, spatial_weight: 0.3}
        requires: ["obsm.spatial"]
        tips:
          - "--resolution: Clustering granularity (default 1.0)."
          - "--spatial-weight: Spatial graph influence (default 0.3)."
      spagcn:
        priority: "spagcn_p → n_domains → epochs"
        params: ["n_domains", "epochs", "spagcn_p"]
        defaults: {n_domains: 7, epochs: 200, spagcn_p: 0.5}
        requires: ["obsm.spatial"]
        tips:
          - "--spagcn-p: Spatial neighborhood contribution (default 0.5)."
          - "--n-domains: Target cluster count."
          - "--epochs: Training loops (default 200)."
      stagate:
        priority: "rad_cutoff/k_nn → stagate_alpha → epochs"
        params: ["n_domains", "epochs", "k_nn", "rad_cutoff", "stagate_alpha", "pre_resolution"]
        defaults: {n_domains: 7, epochs: 200, k_nn: 6, rad_cutoff: 120.0, stagate_alpha: 0.0, pre_resolution: 0.2}
        requires: ["obsm.spatial"]
        tips:
          - "--rad-cutoff / --k-nn: Spatial network. Varies by platform (Visium~150, Slide-seq~50)."
          - "--stagate-alpha: Cell type-aware module weight (0=disabled)."
          - "--epochs: Training epochs."
      graphst:
        priority: "epochs → dim_output → n_domains"
        params: ["n_domains", "epochs", "dim_output"]
        defaults: {n_domains: 7, epochs: 100, dim_output: 64}
        requires: ["obsm.spatial", "raw_or_counts"]
        tips:
          - "--epochs: Default ~600 in official code. Lower to 50-100 for large datasets (>30k spots)."
          - "--dim-output: Embedding dimension (default 64). Increase for complex tissues."
          - "--n-domains: Target cluster count."
      banksy:
        priority: "lambda_param → num_neighbours → resolution"
        params: ["n_domains", "resolution", "lambda_param", "num_neighbours"]
        defaults: {n_domains: 7, resolution: 1.0, lambda_param: 0.2, num_neighbours: 15}
        requires: ["obsm.spatial"]
        tips:
          - "--lambda-param: 0.2 for cell-typing, 0.8 for domain-finding."
          - "--num-neighbours: Spatial geometry k_geom (default 15)."
          - "--resolution / --n-domains: Clustering granularity."
      cellcharter:
        priority: "n_domains/auto_k → n_layers → use_rep"
        params: ["n_domains", "auto_k", "n_layers", "use_rep", "auto_k_min", "auto_k_max"]
        defaults: {n_domains: 7, n_layers: 3, auto_k: false}
        requires: ["obsm.spatial"]
        tips:
          - "--n-layers: Number of spatial hops for feature aggregation (default 3)."
          - "--auto-k: Enable automatic discovery of the most stable cluster count."
          - "--use-rep: Feature representation to use (defaults to X_pca or X)."
    legacy_aliases: [domains]
    saves_h5ad: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🗺️"
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
      - spatial domain
      - tissue region
      - niche
      - SpaGCN
      - STAGATE
      - CellCharter
---

# 🗺️ Spatial Domains

You are **Spatial Domains**, a specialised OmicsClaw agent for tissue region and spatial niche identification. Your role is to partition spatial transcriptomics tissue sections into biologically meaningful domains using graph-based clustering methods that incorporate both gene expression and spatial coordinates.

## Why This Exists

- **Without it**: Users manually configure spatial-aware clustering with inconsistent parameters across methods
- **With it**: One command identifies tissue domains, generates annotated maps, and produces a reproducible report
- **Why OmicsClaw**: Unified interface across Leiden, SpaGCN, STAGATE, and GraphST with consistent output formats

## Core Capabilities

1. **Leiden spatial domains**: Fast graph-based clustering with spatial-weighted neighbors (default)
2. **Louvain clustering**: Classic graph-based clustering (requires louvain package)
3. **SpaGCN**: Spatial Graph Convolutional Network integrating histology
4. **STAGATE**: Graph attention auto-encoder (requires PyTorch Geometric)
5. **GraphST**: Self-supervised contrastive learning (requires PyTorch)
6. **BANKSY**: Explicit spatial feature augmentation (interpretable)
7. **CellCharter**: Neighborhood-aggregated GMM clustering with auto-K selection
8. **Domain visualization**: Spatial scatter plots and UMAP projections colored by domain
9. **Domain summary statistics**: Cell counts and proportions per domain
10. **Spatial refinement**: Optional KNN-based spatial smoothing of domain labels

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (log-norm), `obsm["spatial"]`, `obsm["X_pca"]`, `raw` (counts), `layers["counts"]` | `preprocessed.h5ad` |
| AnnData (raw, demo mode) | `.h5ad` | `X`, `obsm["spatial"]` | `demo_visium.h5ad` |

### Unified Data Convention

After the standard `spatial-preprocess` pipeline, the AnnData object holds
multiple representations of the expression data.  Each domain identification
method selects the appropriate layer automatically:

```
adata.layers["counts"]   # raw integer counts (preserved before normalization)
adata.raw.X              # raw counts (scanpy convention)
adata.X                  # log-normalized expression (normalize_total + log1p)
adata.obsm["X_pca"]      # PCA embeddings (from scaled HVGs)
adata.obsp["connectivities"]  # k-NN neighbor graph (from PCA)
adata.obsm["spatial"]    # spatial coordinates (x, y)
adata.var["highly_variable"]  # HVG annotation
```

### Input Preprocessing Notes

Different methods consume the `preprocessed.h5ad` data differently. The skill
automatically selects the correct data layer for each method:

| Method | Primary input consumed | What the method actually operates on | Extra requirements |
|--------|----------------------|--------------------------------------|-------------------|
| **Leiden** | `obsp["connectivities"]` (neighbor graph) | Pre-built k-NN graph from log-normalized + PCA | Spatial coords for spatial-weighted graph |
| **Louvain** | `obsp["connectivities"]` (neighbor graph) | Pre-built k-NN graph from log-normalized + PCA | Spatial coords optional |
| **SpaGCN** | `X` (log-normalized expression) | Full gene matrix; internal PCA by SpaGCN | Spatial coords required; histology optional |
| **STAGATE** | `X` (log-normalized, HVG subset) | Auto-filters to `var["highly_variable"]` before training | Spatial coords for radius-based adjacency |
| **GraphST** | `raw.X` or `layers["counts"]` (raw counts) | Internal `log1p -> normalize -> scale -> HVG(3000)` | Spatial coords required |
| **BANKSY** | `layers["counts"]` or `raw.X` -> `normalize_total` | Non-negative library-size normalized expression | Spatial coords required |
| **CellCharter** | `obsm["X_pca"]` or `X` (log-normalized) | Fast neighbor aggregation over embeddings | Spatial coords for Delaunay graph |

> **Why raw counts for GraphST?** GraphST's `preprocess()` internally does
> `log1p` + `normalize_total` + `scale` + HVG selection. Passing already
> log-normalized data would cause a double log-transform (`log(log(x+1)+1)`),
> which distorts the expression distribution. The skill automatically restores
> `adata.raw` when available.

> **Why non-negative expression for BANKSY?** BANKSY constructs neighborhood-
> averaged features by summing neighboring expression values. The official
> tutorial uses library-size normalization *without* log or z-score scaling.
> Z-score scaling (`sc.pp.scale`) introduces negative values which distort the
> neighborhood aggregation. The skill restores raw counts and applies
> `normalize_total` (without `log1p`) to produce a non-negative matrix.

## Workflow

1. **Load**: Read preprocessed h5ad; verify spatial coordinates and embeddings exist
2. **Preprocess** (demo mode only): Normalize, log1p, PCA, neighbors if not already done
3. **Domain identification**: Run selected method (Leiden or SpaGCN)
4. **Embed**: Compute UMAP if not present for visualization
5. **Visualize**: Generate spatial domain map and UMAP domain plot
6. **Report**: Write report.md, result.json, processed.h5ad, figures, tables, reproducibility bundle

## CLI Reference

```bash
# Standard usage (Leiden, default)
oc run spatial-domains --input <preprocessed.h5ad> --output <report_dir>

# Specify method and parameters
oc run spatial-domains \
  --input <preprocessed.h5ad> --method leiden --resolution 0.8 --spatial-weight 0.3 --output <dir>

oc run spatial-domains \
  --input <preprocessed.h5ad> --method louvain --resolution 1.0 --output <dir>

oc run spatial-domains \
  --input <preprocessed.h5ad> --method spagcn --n-domains 7 --output <dir>

oc run spatial-domains \
  --input <preprocessed.h5ad> --method stagate --n-domains 7 --k-nn 6 --output <dir>

oc run spatial-domains \
  --input <preprocessed.h5ad> --method graphst --n-domains 7 --output <dir>

oc run spatial-domains \
  --input <preprocessed.h5ad> --method banksy --resolution 0.7 --n-domains 7 --output <dir>

oc run spatial-domains \
  --input <preprocessed.h5ad> --method cellcharter --auto-k --auto-k-min 4 --auto-k-max 12 --output <dir>

# Apply spatial refinement
oc run spatial-domains \
  --input <preprocessed.h5ad> --method leiden --refine --output <dir>

# Demo mode
oc run spatial-domains --demo --output /tmp/domains_demo

# Note: 'oc run' is an alias for 'python omicsclaw.py run'
python omicsclaw.py run spatial-domains --demo
```

## Algorithm / Methodology

### Leiden (default)

1. **Input**: Preprocessed AnnData with spatial coordinates (`adata.obsm["spatial"]`)
2. **Spatial weighting**: Dynamically computes a localized spatial adjacency matrix and merges it with the gene expression neighbor graph without destructively overwriting `adata.obsp["connectivities"]` (preserves downstream UMAPs).
3. **Clustering**: `sc.tl.leiden(adjacency=adjacency, resolution=resolution)`
4. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `resolution`: Controls granularity (default 1.0; higher = more domains)
- `spatial_weight`: Weight of spatial graph (0.0-1.0, default 0.3)

### Louvain

1. **Input**: Preprocessed AnnData with spatial coordinates (`adata.obsm["spatial"]`)
2. **Spatial weighting**: Dynamically computes localized spatial adjacency (restoring feature parity with Leiden) and safely passes it via `adjacency=adjacency`.
3. **Clustering**: `sc.tl.louvain(adjacency=adjacency, resolution=resolution)`
4. **Labels**: Stored in `adata.obs["spatial_domain"]`
5. **Requires**: `pip install louvain`

**Key parameters**:
- `resolution`: Controls granularity (default 1.0)
- `spatial_weight`: Weight of spatial graph (0.0-1.0, default 0.3)

### SpaGCN

1. **Input**: AnnData with spatial coordinates and **log-normalized expression** (following official SpaGCN tutorial: `normalize_per_cell` + `log1p` before training)
2. **Data layer used**: `adata.X` (log-normalized full gene matrix) — SpaGCN performs internal PCA
3. **Spatial graph**: Build adjacency from spatial coordinates
4. **GCN clustering**: `SpaGCN.train()` with `n_domains` target clusters
5. **Refinement**: Built-in spatial-aware label refinement
6. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `n_domains`: Target number of spatial domains
- Source: Hu et al., *Nature Methods* 2021

### STAGATE

1. **Input**: AnnData with spatial coordinates and **log-normalized expression** (auto-subsets to HVGs)
2. **HVG filtering**: If `adata.var["highly_variable"]` exists, only HVGs are used for the autoencoder (reduces VRAM explosion, improves convergence).
3. **Spatial network**: Builds graph preferably using **scale-invariant KNN (`k_nn=6`)** to prevent graph fragmentation across vastly different coordinate scales (e.g. Visium vs Stereo-seq).
4. **Graph attention**: Train attention auto-encoder on PyTorch with aggressive explicit GPU garbage collection to prevent cross-run OOM leaks.
5. **Clustering**: Gaussian Mixture Model on learned embeddings
6. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `n_domains`: Target number of domains
- `k_nn`: Nearest neighbors for spatial topology graph (default 6)
- Source: Dong & Zhang, *Nature Communications* 2022

### GraphST

1. **Input**: AnnData with spatial coordinates (**raw counts** natively sourced from `adata.layers["counts"]` or `adata.raw`)
2. **Raw count restoration**: Automatically restores safe raw counts to avoid double log-transform. (GraphST internally assumes pure counts and runs its own `log1p -> scale -> HVG`).
3. **Preprocessing**: `GraphST.preprocess()` + `GraphST.construct_interaction()`
4. **Contrastive learning**: Self-supervised GNN (with explicit `torch.cuda.empty_cache()` sweeping to prevent VRAM memory locking).
5. **Embedding**: PCA on learned representations.
6. **Clustering**: GMM (with heavily conditioned `reg_covar=1e-3` to prevent ill-conditioned singular matrices) with graceful KMeans fallback.
7. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `n_domains`: Target number of domains
- Source: Long et al., *Nature Communications* 2023

### BANKSY

1. **Input**: AnnData with spatial coordinates
2. **Non-negative normalization**: Restores raw counts from `layers["counts"]`, strictly enforcing `normalize_total` WITHOUT `log1p` to adhere to exact non-negative BANKSY augmentation rules.
3. **HVG Subsetting**: Extremely fast subsetting to HVGs before tensor calculations, yielding orders-of-magnitude reduction in RAM consumption and PCA computation time.
4. **Feature augmentation**: Neighborhood-averaged expression + azimuthal Gabor filters.
5. **Smart Routing Clustering**:
   - If exact `n_domains` is requested: Leverages advanced tied-GMM fallback to guarantee exact cluster slicing.
   - If `n_domains` is NOT requested: Heuristic `sc.tl.leiden` discovery mode via graph density.
6. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `lambda_param`: Spatial regularization (default 0.2)
- `n_domains`: Exact cluster quantity target (optional)
- `resolution`: Leiden resolution (default 0.7, used if n_domains is omitted)
- `num_neighbours`: Neighbors for feature construction (default 15)

> **Note**: Z-score scaling (`sc.pp.scale`) is intentionally **not** applied,
> as it introduces negative values that distort BANKSY's neighborhood feature
> aggregation. See [prabhakarlab/Banksy](https://github.com/prabhakarlab/Banksy).

### CellCharter

1. **Input**: AnnData with spatial coordinates and pre-computed embeddings (preferably `adata.obsm["X_pca"]`).
2. **Spatial Graph**: Constructs a cell-proximity network using Delaunay triangulation. Spurious long-range links are proactively removed (via 99th-percentile edge length thresholding).
3. **Neighborhood Aggregation**: Concatenates each cell's intrinsic features with the mean-aggregated features from its 1-hop, 2-hop, ..., up to `n_layers` (default 3) spatial neighbors.
4. **Clustering**: 
   - **Fixed mode**: Standard Gaussian Mixture Model (GMM) initialization.
   - **Auto-K mode** (`--auto-k`): Performs stability analysis across multiple cluster counts to identify the optimal `n_domains`.
5. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `n_domains`: Target number of domains (ignored if `--auto-k` is true)
- `auto_k`: Enable stability analysis for optimal cluster count
- `n_layers`: Number of spatial neighborhood hops to aggregate (default 3)
- `use_rep`: Feature representation to use (defaults to `X_pca`)
- Source: Marco et al., *Nature Genetics* 2024

### Spatial Refinement (optional)

1. **KNN smoothing**: For each spot, find k nearest spatial neighbors
2. **Majority vote**: Relabel if >threshold fraction of neighbors disagree
3. **Conservative**: Only changes labels with strong spatial disagreement

**Key parameters**:
- `threshold`: Disagreement threshold (default 0.5)
- `k`: Number of spatial neighbors (default 10)

## Example Queries

- "Identify spatial domains in my Visium data"
- "Find tissue regions using SpaGCN"
- "Cluster my spatial transcriptomics data into niches"
- "Run spatial domain detection with 7 clusters"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── spatial_domains.png
│   └── umap_domains.png
├── tables/
│   └── domain_summary.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9 — single-cell/spatial analysis
- `squidpy` >= 1.2 — spatial extensions
- `matplotlib` — plotting
- `numpy`, `pandas` — numerics

**Optional**:
- `SpaGCN` — spatially-aware graph convolutional clustering
- `STAGATE_pyG` — graph attention auto-encoder domains (requires PyTorch)
- `GraphST` — graph self-supervised contrastive learning (requires PyTorch)
- `banksy` — spatial feature augmentation
- `cellcharter` — neighborhood-aggregated clustering and Auto-K selection
- `louvain` — Louvain clustering algorithm

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.
- **Non-destructive**: Domain labels added as new `adata.obs` column, original data preserved

## Integration with Orchestrator

**Trigger conditions**: 
- Automatically invoked dynamically based on tool metadata and user intent matching.
- Keywords — spatial domain, tissue region, niche, SpaGCN, STAGATE

**Chaining partners**:
- `spatial-preprocess`: Provides the preprocessed h5ad input
- `spatial-de`: Downstream differential expression between domains
- `spatial-enrichment`: Gene set enrichment per domain
- `spatial-communication`: Cell-cell communication across domain boundaries

## Citations

- [Scanpy](https://scanpy.readthedocs.io/) — analysis framework
- [Leiden algorithm](https://www.nature.com/articles/s41598-019-41695-z) — community detection
- [SpaGCN](https://doi.org/10.1038/s41592-021-01255-8) — Hu et al., *Nature Methods* 2021
- [STAGATE](https://doi.org/10.1038/s41467-022-29439-6) — Dong & Zhang, *Nature Communications* 2022
- [GraphST](https://doi.org/10.1038/s41467-023-36796-3) — Long et al., *Nature Communications* 2023
- [BANKSY](https://github.com/prabhakarlab/Banksy) — Singhal et al., scalable spatial domain detection
- [CellCharter](https://doi.org/10.1038/s41588-023-01588-4) — Marco et al., *Nature Genetics* 2024
