# Trajectory Methods Guide

## PAGA (Partition-based Graph Abstraction)

PAGA provides a coarse-grained map of cell state transitions by testing statistical significance of connections between cell clusters.

### How it works

1. **Input:** Cluster assignments + cell-cell neighbor graph
2. **Test:** For each pair of clusters, test if the number of inter-cluster edges exceeds what's expected by chance
3. **Output:** Weighted graph where edges represent statistically significant connections

### Key parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| `groups` | required | Cluster key in `adata.obs` |
| `model` | `'v1.2'` | Statistical model for connectivity |

### Interpreting PAGA graphs

- **Thick edges:** Strong connectivity (likely transition path)
- **No edge:** Clusters are not directly connected
- **Hub nodes:** Cell types with multiple connections (branch points)

### PAGA-initialized UMAP

After computing PAGA, use it to initialize UMAP for a trajectory-aware layout:
```python
sc.pl.paga(adata, plot=False)  # Store PAGA positions
sc.tl.umap(adata, init_pos='paga')  # Use PAGA positions as UMAP init
```

This produces UMAP embeddings where cluster relationships better reflect the trajectory topology.

## Diffusion Pseudotime (DPT)

DPT orders cells along a trajectory by computing diffusion distances from a specified root cell.

### How it works

1. **Diffusion map:** Compute diffusion operator from cell-cell neighbor graph
2. **Root selection:** User specifies root cell type → algorithm picks the most extreme cell
3. **Pseudotime:** Compute diffusion distance from root to every cell

### Key parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| `n_dcs` | 10 | Number of diffusion components |
| `iroot` | required | Index of root cell in `adata` |

### Choosing the root cell

The root should be the most primitive/undifferentiated cell type:
- **Stem cells** in differentiation experiments
- **Progenitors** in developmental trajectories
- **Earliest timepoint** in disease progression

For the pancreas dataset: **Ductal** cells are the progenitors.

### Interpreting pseudotime

- **Low pseudotime:** Close to root (early differentiation)
- **High pseudotime:** Far from root (terminal/differentiated)
- **Infinite pseudotime:** Disconnected cells (may need more neighbors)

## Diffusion Maps

Diffusion maps provide a low-dimensional representation that preserves the global structure of the data manifold.

### Advantages over PCA/UMAP for trajectories

| Method | Preserves | Best for |
|--------|-----------|----------|
| PCA | Linear variance | Quick overview, batch effects |
| UMAP | Local structure | Cluster visualization |
| Diffusion map | Global manifold | Trajectory inference, pseudotime |

### Interpreting diffusion components

- **DC1:** Usually captures the primary trajectory axis
- **DC2-3:** Capture branching events or secondary dynamics
- Plotting DC1 vs DC2 often reveals the trajectory structure directly

## Gene-Pseudotime Correlation

Trajectory genes are identified by correlating gene expression with pseudotime.

### Method

1. **Metric:** Spearman rank correlation (robust to non-linear relationships)
2. **Filter:** FDR < 0.05 (Benjamini-Hochberg correction)
3. **Rank:** By absolute correlation strength

### Interpretation

| Correlation | Direction | Meaning |
|-------------|-----------|---------|
| r > 0 | Up | Expression increases along trajectory |
| r < 0 | Down | Expression decreases along trajectory |
| |r| > 0.5 | Strong | Clear temporal dynamic |
| |r| 0.3-0.5 | Moderate | Likely biologically relevant |
| |r| < 0.3 | Weak | May be noise |
