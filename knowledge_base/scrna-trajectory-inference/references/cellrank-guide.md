# CellRank Guide

## Overview

CellRank computes cell fate probabilities by combining RNA velocity (or pseudotime) with the cell-cell similarity graph. It identifies terminal states, computes absorption probabilities, and discovers lineage driver genes.

## Kernels

CellRank uses "kernels" to model cell state transitions:

### VelocityKernel (preferred when velocity available)
- Uses RNA velocity to infer transition probabilities
- Captures directionality of cell state changes
- Combined with ConnectivityKernel for robustness

### PseudotimeKernel (fallback)
- Uses diffusion pseudotime to define transition direction
- Good when velocity data is unavailable
- Assumes monotonic progression (no backtracking)

### ConnectivityKernel
- Based on cell-cell similarity (k-NN graph)
- Undirected — provides smoothing
- Always combined with a directional kernel (0.8/0.2 weight)

## Analysis Pipeline

1. **Compute transition matrix** from chosen kernel(s)
2. **Estimate terminal states** using GPCCA (Generalized Perron Cluster Cluster Analysis)
3. **Compute fate probabilities** — for each cell, probability of reaching each terminal state
4. **Identify driver genes** — genes correlated with fate commitment

## Key Outputs

### Terminal states
Cell types identified as endpoints of the trajectory. CellRank auto-detects these from the transition matrix structure.

### Fate probabilities
Per-cell matrix: rows = cells, columns = terminal states. Each row sums to 1.

| Probability | Interpretation |
|-------------|---------------|
| >0.8 | Strongly committed to this fate |
| 0.4-0.8 | Partially committed |
| <0.4 | Uncommitted (progenitor-like) |

### Driver genes
Genes whose expression correlates with commitment to a specific fate. Top drivers are often known fate-determining transcription factors.

## Interpreting CellRank Results

### Fate probability UMAPs
Each panel shows cells colored by probability of reaching a specific terminal state. Gradient from blue (low) to red (high).

### Fate heatmap
Mean fate probability per cell type. Shows which cell types are committed to which fates, and which are multipotent.

### Driver genes
Bar plots showing top genes correlated with each fate. Validate against known biology:
- **Alpha cell fate:** GCG, ARX, IRX1
- **Beta cell fate:** INS, NKX6-1, PDX1, MAFA
- **Delta cell fate:** SST, HHEX

## Common Issues

| Issue | Solution |
|-------|----------|
| Wrong terminal states | Check PAGA graph — terminal states should be leaf nodes |
| All cells committed | May need earlier timepoint cells as progenitors |
| CellRank import error | `pip install cellrank` — check scipy version compatibility |
| Memory error | Reduce to fewer cells or fewer PCs |

## Version Compatibility

CellRank 2.0+ uses a different API from CellRank 1.x:
- Use `cr.kernels.VelocityKernel` (not `cr.tl.transition_matrix`)
- Use `cr.estimators.GPCCA` (not `cr.tl.terminal_states`)
- The scripts use the CellRank 2.0+ API
