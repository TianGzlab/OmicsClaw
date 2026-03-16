# sc-velocity — RNA Velocity Analysis

## Purpose

Estimate the future state of cells by analyzing spliced and unspliced mRNA counts using **scVelo**:

- **Velocity estimation** — direction and speed of transcriptional change
- **Velocity graph** — cell-to-cell transition probabilities
- **Latent time** — global transcriptomic time (dynamical mode only)

RNA velocity provides dynamic information beyond static snapshots.

## When to Use

- Developmental biology and lineage tracing
- Cell state transition analysis
- Identifying direction of differentiation
- Validating pseudotime trajectories

## Requirements

- **Input**: AnnData with:
  - `layers["spliced"]` — spliced mRNA counts
  - `layers["unspliced"]` — unspliced mRNA counts
  - Preprocessed (normalized, log-transformed)

- **Dependencies**:
  - scvelo (required)
  - scanpy, numpy, scipy

### Generating Spliced/Unspliced Data

For 10X data, use one of:
- **velocyto**: `velocyto run10x sample_name/ refdata-cellranger-mm10-3.0.0/genes/genes.gtf`
- **kb-python**: `kb count -i index.idx -g t2g.txt -x 10xv2 -o output --lamanno`

## Usage

### CLI

```bash
# Basic usage (stochastic mode)
python omicsclaw.py run sc-velocity --input data_with_spliced.h5ad --output results/

# Dynamical mode (slower, computes latent time)
python omicsclaw.py run sc-velocity --input data.h5ad --output results/ --mode dynamical

# Demo mode (synthetic data)
python omicsclaw.py run sc-velocity --demo --output /tmp/velocity_demo/
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | required | Input AnnData with spliced/unspliced layers |
| `--output` | required | Output directory |
| `--demo` | false | Run with synthetic demo data |
| `--mode` | stochastic | Velocity mode: stochastic, dynamical, steady_state |
| `--n-jobs` | 4 | Number of parallel jobs |

### Modes

| Mode | Speed | Features | When to Use |
|------|-------|----------|-------------|
| `stochastic` | Fast | Velocity vectors | Quick analysis, large datasets |
| `dynamical` | Slow | Velocity + latent time | Full trajectory, publication |
| `steady_state` | Fastest | Basic velocity | Very large datasets |

## Output Structure

```
output_dir/
├── adata_with_velocity.h5ad      # AnnData with velocity results
├── report.md                      # Analysis report
├── result.json                    # Machine-readable results
├── figures/
│   ├── velocity_stream.png       # Velocity stream plot on UMAP
│   ├── velocity_magnitude_umap.png
│   └── latent_time_umap.png      # (dynamical mode only)
└── reproducibility/
    ├── commands.sh
    └── environment.yml
```

## Methods

### RNA Velocity

RNA velocity estimates transcriptional dynamics by comparing spliced (mature) and unspliced
(nascent) mRNA abundances.

- **High velocity** → active transcription of gene
- **Negative velocity** → gene being downregulated
- **Stream arrows** → direction of future state

### Latent Time (Dynamical Mode Only)

Latent time is a global, transcriptome-wide pseudotime learned from the dynamical model.
Unlike DPT pseudotime, it accounts for splicing kinetics.

## Interpretation

1. **Stream arrows**: Point toward future cell states
2. **Velocity magnitude**: High values indicate active transcriptional changes
3. **Latent time**: Trajectory from early (0) to late (1) states
4. **Branches**: Arrows pointing in different directions indicate bifurcations

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No spliced/unspliced layers | Run velocyto or kb-python with `--lamanno` |
| scVelo not installed | `pip install scvelo` |
| Too few genes pass filtering | Check data quality, reduce `min_shared_counts` |
| Slow dynamical mode | Use `stochastic` mode for exploration |

## Tips

- Preprocess data with `sc-preprocessing` first
- Velocity works best on raw counts (not normalized)
- Combine with `sc-pseudotime` for static trajectory comparison
- Use `dynamical` mode for final analysis, `stochastic` for exploration

## References

- Bergen et al. (2020) Generalizing RNA velocity to transient cell states through dynamical modeling
- La Manno et al. (2018) RNA velocity of single cells
