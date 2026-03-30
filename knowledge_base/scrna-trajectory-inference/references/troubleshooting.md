# Troubleshooting Guide

## Installation Issues

### scVelo installation fails
```
pip install scvelo
```
If compilation errors occur, try:
```
pip install --no-build-isolation scvelo
```
Or install via conda: `conda install -c conda-forge scvelo`

### CellRank version conflict with scipy
CellRank 2.0+ may conflict with scipy versions. Fix:
```
pip install cellrank scipy>=1.7,<1.12
```

### reportlab for PDF reports
```
pip install reportlab
```
If PDF generation fails, the markdown report is always generated as fallback.

## Data Issues

### "Root cell type not found"
**Cause:** The `root_cell_type` parameter doesn't match any value in the cluster column.

**Fix:** Check available cell types:
```python
print(adata.obs['clusters'].unique())
```
Use the exact string (case-sensitive).

### "Too few cells" error
**Cause:** Dataset has fewer than 200 cells.

**Fix:** Trajectory inference needs sufficient cells to estimate a manifold. Consider:
- Removing overly strict QC filters
- Combining batches if appropriate
- Using a different analysis approach for very small datasets

### No spliced/unspliced layers
**Cause:** The input h5ad doesn't contain RNA velocity layers.

**Impact:** RNA velocity (scVelo) will be skipped. Core trajectory (PAGA + pseudotime) still works.

**Fix:** Re-process raw data with:
- STARsolo with `--soloFeatures Gene Velocyto`
- velocyto on Cell Ranger BAM output

### Infinite pseudotime values
**Cause:** Some cells are disconnected from the root cell in the neighbor graph.

**Fix:**
- Increase `n_neighbors` (default 30 → try 50)
- Check for distinct batches that aren't connected
- Remove very small outlier clusters

## Analysis Issues

### scVelo dynamical model fails
**Cause:** Insufficient unspliced counts or too few cells with detectable dynamics.

**Impact:** Script automatically falls back to stochastic model (faster, less accurate).

**Verify:** Check unspliced fraction:
```python
import numpy as np
unspliced = adata.layers['unspliced']
if hasattr(unspliced, 'toarray'):
    unspliced = unspliced.toarray()
frac = (unspliced > 0).sum() / unspliced.size
print(f"Fraction of non-zero unspliced: {frac:.3f}")
# Should be > 0.05 for meaningful velocity
```

### CellRank identifies wrong terminal states
**Cause:** Auto-detection based on transition matrix may not match expected biology.

**Verify:** Check PAGA graph — terminal states should be leaf nodes (not hubs).

**Fix options:**
1. Manually specify terminal states in CellRank
2. Adjust cluster resolution
3. Remove confounding cell populations

### Few trajectory genes found
**Cause:** Weak signal or homogeneous dataset.

**Try:**
- Lower FDR threshold to 0.1
- Use more highly variable genes in preprocessing
- Check if the trajectory is biologically meaningful (not all datasets have trajectories)

### Velocity arrows point in unexpected direction
**Cause:** Cell cycle effects, technical artifacts, or genuine biology.

**Try:**
1. Regress out cell cycle genes: `sc.pp.regress_out(adata, ['S_score', 'G2M_score'])`
2. Check velocity confidence plot — low-confidence cells may have unreliable arrows
3. Consider if the biology supports the observed direction

## Plotting Issues

### SVG export fails
**Impact:** PNG files are always generated. SVG failure is handled gracefully.

**If you need SVG:**
```
pip install cairosvg
```

### Empty or blank plots
**Cause:** Usually a matplotlib backend issue.

**Fix:** The scripts set `matplotlib.use("Agg")` (non-interactive). If running interactively:
```python
import matplotlib
matplotlib.use("Agg")  # Before importing pyplot
```

### Heatmap too large or slow
**Cause:** Too many genes or cells.

**Fix:** The script auto-subsamples to 500 cells and 50 genes. For larger views, edit the parameters in `generate_all_plots.py`.

## Performance

### Analysis takes too long
Expected runtimes for ~3,700 cells (pancreas dataset):
| Step | Time |
|------|------|
| PAGA + DPT | ~30 seconds |
| scVelo stochastic | ~1 min |
| scVelo dynamical | ~5-10 min |
| CellRank | ~2-3 min |
| Plotting | ~1-2 min |
| Total (full) | ~10-15 min |

For larger datasets (>20,000 cells), consider:
- Using stochastic velocity model
- Subsampling for CellRank
- Running on a machine with more RAM

### Memory issues
For datasets >50,000 cells:
- Use sparse matrices throughout
- Process chromosomes/gene sets in batches
- Consider downsampling to 20,000-30,000 cells


---
