---
name: spatial-trajectory
description: >-
  Trajectory inference and pseudotime analysis using DPT, Monocle3, Slingshot, scVelo
  for RNA velocity, and PAGA for abstracted graph analysis.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, trajectory, pseudotime, DPT, CellRank, Monocle3, scVelo, Slingshot]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🛤️"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - trajectory inference
      - pseudotime
      - DPT
      - Monocle
      - CellRank
      - Slingshot
      - RNA velocity
      - scVelo
---

# 🛤️ Single-Cell Trajectory Inference

You are **SC Trajectory**, a specialised OmicsClaw agent for trajectory inference and pseudotime ordering in single-cell data.

## Why This Exists

- **Without it**: Understanding cellular differentiation dynamics requires complex multi-step analysis
- **With it**: Automated trajectory and pseudotime computation with publication-ready visualisations
- **Why OmicsClaw**: Standardised trajectory analysis across datasets and methods

## Core Capabilities

1. **DPT** (Diffusion Pseudotime): Built-in via Scanpy — fast, robust
2. **PAGA**: Partition-based graph abstraction for coarse-grained trajectories
3. **Monocle3** (R): Principal graph learning with branch point analysis
4. **Slingshot** (R): Minimum spanning tree + principal curves for smooth lineages
5. **scVelo** (Python): RNA velocity — spliced/unspliced dynamics for cell fate prediction
6. **CellRank**: Fate mapping combining RNA velocity with transcriptomic similarity

## Input Formats

| Format | Extension | Required |
|--------|-----------|----------|
| AnnData | `.h5ad` | Pre-processed (PCA/UMAP done) |
| Loom | `.loom` | With spliced/unspliced layers (for scVelo) |

## Workflow

1. **Calculate**: Set root parameters and infer lineage topology frameworks.
2. **Execute**: Determine pseudotime distance coordinates for all viable paths.
3. **Assess**: Perform branching statistics and gene transition cascades.
4. **Visualise**: Create vector maps (RNA-Velocity) or abstraction curves (PAGA).
5. **Report**: Write metrics defining dynamic differential behaviors.

## CLI Reference

```bash
python skills/singlecell/trajectory/sc_trajectory.py \
  --input <processed.h5ad> --output <dir>
python omicsclaw.py run sc-trajectory --demo
```

## Algorithm / Methodology

### DPT with PAGA (Scanpy — Python)

**Goal:** Compute diffusion pseudotime and use PAGA for coarse-grained trajectory visualization.

```python
import scanpy as sc
import numpy as np

# Compute PAGA
sc.tl.paga(adata, groups='leiden')
sc.pl.paga(adata, color='leiden', threshold=0.03)

# PAGA-initialized UMAP
sc.tl.draw_graph(adata, init_pos='paga')
sc.pl.draw_graph(adata, color='leiden')

# Diffusion pseudotime
adata.uns['iroot'] = np.flatnonzero(adata.obs['leiden'] == 'root_cluster')[0]
sc.tl.dpt(adata)
sc.pl.draw_graph(adata, color='dpt_pseudotime')
```

### Monocle3 (R)

**Goal:** Infer developmental trajectories and pseudotime ordering using Monocle3's principal graph approach.

**Approach:** Learn a principal graph through the data manifold, order cells along the graph from a root state, and extract pseudotime values.

```r
library(monocle3)

# Create cell_data_set from Seurat
cds <- as.cell_data_set(seurat_obj)

# Preprocess (if not already done)
cds <- preprocess_cds(cds, num_dim = 50)
cds <- reduce_dimension(cds, reduction_method = 'UMAP')

# Cluster cells
cds <- cluster_cells(cds)

# Learn trajectory graph
cds <- learn_graph(cds)

# Order cells (select root interactively or programmatically)
cds <- order_cells(cds, root_cells = root_cell_ids)

# Plot trajectory with pseudotime
plot_cells(cds, color_cells_by = 'pseudotime', label_branch_points = TRUE, label_leaves = TRUE)

# Get pseudotime values
pseudotime <- pseudotime(cds)
```

#### Set Root Programmatically

```r
# Find root by progenitor cluster
get_earliest_principal_node <- function(cds, cluster_name) {
    cell_ids <- which(colData(cds)$seurat_clusters == cluster_name)
    closest_vertex <- cds@principal_graph_aux[['UMAP']]$pr_graph_cell_proj_closest_vertex
    closest_vertex <- as.matrix(closest_vertex[cell_ids, ])
    root_pr_nodes <- igraph::V(principal_graph(cds)[['UMAP']])$name[
        as.numeric(names(which.max(table(closest_vertex))))]
    root_pr_nodes
}

cds <- order_cells(cds, root_pr_nodes = get_earliest_principal_node(cds, 'stem_cluster'))
```

### Slingshot (R)

**Goal:** Infer smooth lineage trajectories and pseudotime using minimum spanning tree and principal curves.

```r
library(slingshot)
library(SingleCellExperiment)

# From Seurat object
sce <- as.SingleCellExperiment(seurat_obj)
reducedDims(sce)$UMAP <- Embeddings(seurat_obj, 'umap')

# Run slingshot
sce <- slingshot(sce, clusterLabels = 'seurat_clusters', reducedDim = 'UMAP')

# Get pseudotime for each lineage
pseudotime_mat <- slingPseudotime(sce)

# Get lineage curves
curves <- slingCurves(sce)

# Specify start and end clusters
sce <- slingshot(sce, clusterLabels = 'seurat_clusters', reducedDim = 'UMAP',
                 start.clus = 'HSC', end.clus = c('Erythroid', 'Myeloid'))
```

### scVelo RNA Velocity (Python)

**Goal:** Estimate RNA velocity to predict future cell states from spliced/unspliced transcript ratios.

**Approach:** Model the dynamics of splicing using stochastic or dynamical models, compute velocity vectors, and project directional flow onto UMAP.

```python
import scvelo as scv
import scanpy as sc

# Load data with spliced/unspliced counts
adata = scv.read('data.h5ad')

# Or merge loom files from velocyto
ldata = scv.read('velocyto_output.loom')
adata = scv.utils.merge(adata, ldata)

# Preprocess
scv.pp.filter_and_normalize(adata, min_shared_counts=20, n_top_genes=2000)
scv.pp.moments(adata, n_pcs=30, n_neighbors=30)

# Compute velocity (stochastic model)
scv.tl.velocity(adata, mode='stochastic')
scv.tl.velocity_graph(adata)

# Visualize velocity streams
scv.pl.velocity_embedding_stream(adata, basis='umap', color='clusters')
```

#### scVelo Dynamical Model (More Accurate)

```python
# More accurate but slower
scv.tl.recover_dynamics(adata, n_jobs=8)
scv.tl.velocity(adata, mode='dynamical')
scv.tl.velocity_graph(adata)

# Latent time (pseudotime)
scv.tl.latent_time(adata)
scv.pl.scatter(adata, color='latent_time', cmap='gnuplot')

# Velocity confidence
scv.tl.velocity_confidence(adata)
scv.pl.scatter(adata, color=['velocity_confidence', 'velocity_length'])
```

### Gene Dynamics Along Trajectory

```r
# Monocle3: Find genes varying over pseudotime
graph_test_res <- graph_test(cds, neighbor_graph = 'principal_graph', cores = 4)
sig_genes <- graph_test_res %>% filter(q_value < 0.05) %>% arrange(desc(morans_I))

# Plot gene expression over pseudotime
plot_genes_in_pseudotime(cds[rownames(cds) %in% top_genes, ], color_cells_by = 'cluster')
```

```python
# scVelo: Top likelihood genes
scv.tl.rank_velocity_genes(adata, groupby='clusters', min_corr=0.3)
top_genes = adata.uns['rank_velocity_genes']['names']

# Plot phase portraits
scv.pl.velocity(adata, var_names=['gene1', 'gene2'], basis='umap')
```

### Branch Point Analysis

```r
# Slingshot + tradeSeq for branch analysis
library(tradeSeq)
sce <- fitGAM(sce, nknots = 6)
branch_res <- earlyDETest(sce, knots = c(3, 4))
```

### Velocyto Preprocessing

```bash
# Generate loom file with spliced/unspliced counts
velocyto run10x -m repeat_mask.gtf /path/to/cellranger_output annotation.gtf

# For SmartSeq2
velocyto run_smartseq2 -o output -m repeat_mask.gtf -e sample bam_files/*.bam annotation.gtf
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `dpt` | Method: dpt, paga, monocle3, slingshot, scvelo |
| `--root-cluster` | auto | Root cluster for pseudotime |
| `--n-dcs` | `15` | Diffusion components |
| `--velocity-mode` | `stochastic` | scVelo mode: stochastic, dynamical, deterministic |

## Example Queries

- "Compute cellular trajectories via DPT pseudotime"
- "Infer branching timelines using Monocle3 principal graphs"

## Version Compatibility

Reference examples tested with: scanpy 1.10+, scvelo 0.3+, cellrank 2.0+

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── summary_plot.png
├── tables/
│   └── metrics.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required**: scanpy >= 1.9
**Optional**: scvelo, cellrank, monocle3 (R), slingshot (R), tradeSeq (R)

## Citations

- [DPT](https://doi.org/10.1038/nmeth.3971) — Haghverdi et al., Nature Methods 2016
- [PAGA](https://doi.org/10.1186/s13059-019-1663-x) — Wolf et al., Genome Biology 2019
- [Monocle3](https://doi.org/10.1038/s41586-019-0969-x) — Cao et al., Nature 2019
- [Slingshot](https://doi.org/10.1186/s12864-018-4772-0) — Street et al., BMC Genomics 2018
- [scVelo](https://doi.org/10.1038/s41587-020-0591-3) — Bergen et al., Nature Biotechnology 2020
- [CellRank](https://cellrank.readthedocs.io/) — Lange et al., Nature Methods 2022

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `sc-preprocess` — Prerequisite preprocessing
- `sc-communication` — Communication along trajectory
- `sc-de` — Differential expression along pseudotime
