# RNA Velocity Guide

## Overview

RNA velocity estimates the rate and direction of gene expression change in individual cells by modeling the ratio of unspliced to spliced mRNA.

## How RNA Velocity Works

1. **Splicing kinetics:** Newly transcribed pre-mRNA (unspliced) is processed into mature mRNA (spliced)
2. **Steady state:** If transcription rate is constant, unspliced/spliced ratio reaches equilibrium
3. **Velocity:** Cells deviating from steady state are transitioning — the deviation direction indicates where the cell is heading

## scVelo Models

### Stochastic model (default fallback)
- Fits a linear steady-state model per gene
- Fast (~1 min for 3,000 cells)
- Assumes constant transcription/degradation rates
- Good for: Quick overview, large datasets

### Dynamical model (preferred)
- Fits a full kinetic ODE model per gene
- Slower (~5-10 min for 3,000 cells)
- Captures transient dynamics, time-varying rates
- Provides **latent time** (velocity-based pseudotime)
- Good for: Publication results, complex trajectories

### When dynamical model fails

Common reasons:
- Too few cells with unspliced counts
- Low-quality spliced/unspliced estimates
- Very short trajectory (insufficient dynamics)

**Fallback:** Script automatically switches to stochastic model.

## Required Data

RNA velocity needs **spliced** and **unspliced** count matrices:

| Tool | Produces | Format |
|------|----------|--------|
| Cell Ranger | Spliced/unspliced in BAM | Needs velocyto |
| STARsolo | `--soloFeatures Gene Velocyto` | Direct |
| velocyto | Loom file | `scv.read_loom()` |
| alevin-fry | Spliced/unspliced quantification | Direct |

## Key Outputs

### Velocity stream plot
Arrows on UMAP showing direction of cell state transitions. The most visually informative velocity plot.

### Velocity confidence
Per-cell score (0-1) indicating reliability of velocity estimate:
- **>0.8:** High confidence
- **0.5-0.8:** Moderate
- **<0.5:** Unreliable velocity for this cell

### Latent time (dynamical model only)
scVelo's estimate of a cell's position along the trajectory, independent of diffusion pseudotime. Often correlates well with DPT but uses different information (RNA dynamics vs. diffusion distances).

### Top velocity genes
Genes with highest fit likelihood in the dynamical model — these drive the observed velocity patterns.

## Interpreting Velocity Streams

| Pattern | Interpretation |
|---------|---------------|
| Coherent arrows pointing one direction | Clear differentiation trajectory |
| Converging arrows | Terminal/stable state |
| Diverging arrows | Branch point or fate decision |
| Random/chaotic arrows | No clear trajectory (or poor velocity estimates) |
| Counter-intuitive direction | May indicate dedifferentiation or cell cycle effects |

## Caveats

1. **Cell cycle:** Can dominate velocity signals. Consider regressing out cell cycle genes.
2. **Low unspliced counts:** Some 10x datasets have very few unspliced reads → unreliable velocity.
3. **Steady-state cells:** Terminally differentiated cells in steady state show zero velocity (expected).
4. **Technical artifacts:** Library prep and sequencing depth affect unspliced/spliced ratio.
