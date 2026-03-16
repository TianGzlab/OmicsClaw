# sc-pseudotime — Pseudotime Trajectory Analysis

## Purpose

Infer temporal ordering and trajectory structure of single-cell data using:
- **PAGA** (Partition-based Graph Abstraction) — cluster connectivity
- **Diffusion Map** — non-linear dimensionality reduction
- **DPT** (Diffusion Pseudotime) — pseudotemporal ordering

This is a core trajectory analysis skill that works with standard scanpy preprocessing.

## When to Use

- Lineage tracing and developmental biology studies
- Cell differentiation trajectory inference
- Identifying trajectory-associated genes
- Understanding cell state transitions

## Requirements

- **Input**: AnnData with:
  - Preprocessed data (normalized, log-transformed)
  - PCA computed
  - Neighbor graph computed
  - Cluster labels (e.g., `leiden`)

- **Dependencies**:
  - scanpy (required)
  - numpy, pandas, scipy (required)

## Usage

### CLI

```bash
# Basic usage
python omicsclaw.py run sc-pseudotime --input preprocessed.h5ad --output results/

# With specific root cluster
python omicsclaw.py run sc-pseudotime --input data.h5ad --output results/ --root-cluster "0"

# Demo mode
python omicsclaw.py run sc-pseudotime --demo --output /tmp/pseudotime_demo/
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | required | Input AnnData file (.h5ad) |
| `--output` | required | Output directory |
| `--demo` | false | Run with synthetic demo data |
| `--cluster-key` | `leiden` | Key for cluster labels |
| `--root-cluster` | auto | Root cluster for pseudotime |
| `--root-cell` | auto | Root cell index (overrides --root-cluster) |
| `--n-dcs` | 10 | Number of diffusion components |
| `--n-genes` | 50 | Number of trajectory genes to find |
| `--method` | pearson | Correlation method (pearson/spearman) |

## Output Structure

```
output_dir/
├── adata_with_trajectory.h5ad    # AnnData with pseudotime + diffmap
├── report.md                      # Analysis report
├── result.json                    # Machine-readable results
├── figures/
│   ├── paga_graph.png            # PAGA connectivity graph
│   ├── pseudotime_umap.png       # Pseudotime on UMAP
│   ├── diffusion_components.png  # Diffusion map components
│   └── trajectory_gene_heatmap.png
├── tables/
│   └── trajectory_genes.csv      # Genes correlated with pseudotime
└── reproducibility/
    ├── commands.sh
    └── environment.yml
```

## Methods

### PAGA (Partition-based Graph Abstraction)

PAGA estimates the connectivity between clusters by quantifying how much the single-cell graph
connectivity at each cluster resolution is preserved at a coarser resolution.

- **Input**: Neighbor graph + cluster labels
- **Output**: Weighted graph of cluster connectivities
- **Interpretation**: Thick edges indicate strong connectivity (likely transition path)

### Diffusion Map

Diffusion maps provide a non-linear dimensionality reduction that preserves the underlying
manifold structure of single-cell data.

- **Input**: PCA-reduced data
- **Output**: Diffusion components (DC1, DC2, ...)
- **Interpretation**: Cells close in diffusion space are transcriptionally similar

### DPT (Diffusion Pseudotime)

DPT uses random walks on the diffusion graph to estimate pseudotemporal ordering of cells
from a root cell.

- **Input**: Diffusion map + root cell
- **Output**: Pseudotime values [0, 1]
- **Interpretation**: 0 = root state, 1 = terminal state

## Interpretation

1. **PAGA graph**: Look for linear chains (lineages) or branching points (bifurcations)
2. **Pseudotime UMAP**: Gradient from root (0) to terminal (1) cells
3. **Trajectory genes**: Genes correlated with pseudotime may be drivers of transition

## Tips

- Choose root cluster/cell based on known biology (e.g., stem cells, early progenitors)
- Use `sc-velocity` for RNA velocity-based trajectory if spliced/unspliced data available
- Combine with `sc-grn` to find TFs driving trajectory transitions

## References

- Wolf et al. (2019) PAGA: graph abstraction reconciles clustering with trajectory inference
- Haghverdi et al. (2016) Diffusion maps for high-dimensional single-cell data
- Haghverdi et al. (2016) Diffusion pseudotime
