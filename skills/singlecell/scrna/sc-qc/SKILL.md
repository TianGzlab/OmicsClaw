---
name: sc-qc
description: >-
  Quality control metrics calculation and visualization for single-cell RNA-seq
  data. Computes QC metrics (genes, UMIs, mitochondrial/ribosomal content) and
  generates diagnostic plots. Does NOT filter cells.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [singlecell, QC, quality control, metrics, visualization]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "📊"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - QC metrics
      - quality control
      - calculate QC
      - QC visualization
      - violin plots QC
      - mitochondrial percentage
      - n genes per cell
---

# 📊 Single-Cell QC Metrics

Calculate and visualize quality control metrics for single-cell RNA-seq data. This skill provides comprehensive QC assessment WITHOUT filtering — use `sc-preprocessing` for actual cell filtering.

## Why This Exists

- **Without it**: No systematic way to assess data quality before filtering decisions
- **With it**: Comprehensive QC metrics and visualizations to guide filtering thresholds
- **Why OmicsClaw**: Species-aware mitochondrial detection, ribosomal metrics, and publication-ready plots

## Core Capabilities

1. **QC Metric Calculation**: n_genes_by_counts, total_counts, pct_counts_mt, pct_counts_ribo
2. **Violin Plots**: Distribution visualization of QC metrics
3. **Scatter Plots**: Relationships between total_counts, n_genes, and mitochondrial percentage
4. **Histograms**: Distribution with median indicators
5. **Top Expressed Genes**: Identify highly expressed genes and potential contaminants

## Workflow

1. **Load Data**: Read AnnData object (h5ad, 10X mtx, loom, or CSV)
2. **Calculate Metrics**: Compute QC metrics with species-aware mitochondrial detection
3. **Generate Plots**: Create diagnostic visualizations
4. **Export Summary**: Save per-cell metrics and summary statistics
5. **Report**: Comprehensive markdown report with interpretation guidance

## CLI Reference

```bash
# Basic usage
python skills/singlecell/scrna/sc-qc/sc_qc.py --input <data.h5ad> --output <dir>

# With demo data
python skills/singlecell/scrna/sc-qc/sc_qc.py --demo --output /tmp/qc_demo

# Specify species
python skills/singlecell/scrna/sc-qc/sc_qc.py --input <data.h5ad> --output <dir> --species mouse

# Via omicsclaw CLI
python omicsclaw.py run sc-qc --input <data.h5ad> --output <dir>
```

## Algorithm / Methodology

### QC Metrics Calculation

```python
import scanpy as sc
import numpy as np

# Species-specific mitochondrial gene patterns
species_patterns = {
    'human': 'MT-',      # MT-ND1, MT-CO1, etc.
    'mouse': 'mt-'       # mt-Nd1, mt-Co1, etc.
}

# Ribosomal gene patterns
ribo_patterns = {
    'human': '^RP[SL]',  # RPS1, RPL1, etc.
    'mouse': '^Rp[sl]'   # Rps1, Rpl1, etc.
}

# Identify mitochondrial genes
adata.var['mt'] = adata.var_names.str.startswith(mito_pattern)

# Identify ribosomal genes (optional)
adata.var['ribo'] = adata.var_names.str.match(ribo_pattern)

# Calculate QC metrics
sc.pp.calculate_qc_metrics(
    adata,
    qc_vars=['mt', 'ribo'],
    percent_top=None,
    log1p=False,
    inplace=True
)

# Add log-transformed metrics
adata.obs['log10_total_counts'] = np.log10(adata.obs['total_counts'] + 1)
adata.obs['log10_n_genes_by_counts'] = np.log10(adata.obs['n_genes_by_counts'] + 1)
```

### Generated QC Metrics

| Metric | Description |
|--------|-------------|
| `n_genes_by_counts` | Number of unique genes detected per cell |
| `total_counts` | Total UMI counts per cell |
| `pct_counts_mt` | Percentage of counts from mitochondrial genes |
| `pct_counts_ribo` | Percentage of counts from ribosomal genes |
| `log10_total_counts` | Log10-transformed total counts |
| `log10_n_genes_by_counts` | Log10-transformed gene count |

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | required | Input AnnData file |
| `--output` | required | Output directory |
| `--demo` | false | Run with demo data |
| `--species` | human | Species for MT gene detection (human/mouse) |

## Example Queries

- "Calculate QC metrics for this data"
- "Visualize QC distributions"
- "Show mitochondrial percentage distribution"
- "Generate QC violin plots"
- "What are the quality metrics for this dataset?"

## Output Structure

```
output_dir/
├── report.md                    # Comprehensive QC report
├── result.json                  # Structured results
├── qc_checked.h5ad              # AnnData with QC metrics in .obs
├── figures/
│   ├── qc_violin.png            # Violin plots of QC metrics
│   ├── qc_scatter.png           # Scatter plots (counts vs genes, MT%)
│   ├── qc_histograms.png        # Distribution histograms
│   └── highest_expr_genes.png   # Top 20 expressed genes
├── tables/
│   ├── qc_metrics_summary.csv   # Summary statistics
│   └── qc_metrics_per_cell.csv  # Per-cell QC values
└── reproducibility/
    ├── commands.sh              # Command to reproduce
    └── environment.yml          # Package versions
```

## Interpretation Guidance

### N Genes by Counts

| Range | Interpretation |
|-------|----------------|
| < 200 | Likely empty droplets or dead cells |
| 200 - 2500 | Typical for PBMC |
| 200 - 6000 | Typical for brain/neurons |
| > 6000 | Possible doublets |

### Mitochondrial Percentage

| Range | Interpretation |
|-------|----------------|
| < 5% | Healthy cells |
| 5 - 10% | Moderate stress |
| 10 - 20% | High stress, may still be valid |
| > 20% | Likely dying/dead cells |

### Tissue-Specific Thresholds

| Tissue | Max MT% | Notes |
|--------|---------|-------|
| PBMC | 5% | Blood cells, low MT expected |
| Brain | 10% | Neurons have complex transcripts |
| Tumor | 20% | Heterogeneous, higher MT tolerated |
| Heart | 15% | Cardiomyocytes naturally high MT |
| Liver/Kidney | 15% | Metabolic tissues |

## Workflow Integration

This skill is typically followed by:

1. **sc-preprocessing** — Applies filtering based on QC thresholds
2. **sc-doublet-detection** — Identifies doublets before/after filtering
3. **sc-batch-integration** — Integration after QC filtering

### Recommended Order

```
sc-qc → (review metrics) → sc-preprocessing → sc-doublet-detection → downstream analysis
```

## Method Comparison

| Approach | Use Case |
|----------|----------|
| Fixed thresholds | Well-characterized tissues with established guidelines |
| MAD outlier detection | Multi-batch data with batch-specific distributions |
| Manual inspection | Novel data types, exploratory analysis |

## Dependencies

**Required**: scanpy, numpy, pandas, matplotlib, seaborn

**Optional**: None (all visualization uses matplotlib/seaborn)

## Citations

- [Scanpy QC](https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.calculate_qc_metrics.html) — Wolf et al., 2018
- [Best practices](https://doi.org/10.15252/msb.20188746) — Luecken & Theis, Mol Syst Biol 2019

## Safety

- **No filtering**: This skill only calculates metrics, does not modify cell counts
- **Local-first**: All processing is local, no data upload
- **Audit trail**: Complete provenance in reproducibility/ directory

## Integration with Orchestrator

**Trigger conditions**:
- User asks about QC metrics without mentioning filtering
- Initial data quality assessment
- Pre-filtering visualization

**Chaining partners**:
- `sc-preprocessing` — After reviewing QC metrics
- `sc-doublet-detection` — Before or after preprocessing
- `sc-annotation` — After complete preprocessing pipeline
