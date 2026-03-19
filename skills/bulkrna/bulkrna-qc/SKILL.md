---
name: bulkrna-qc
description: >-
  Bulk RNA-seq count matrix quality control — library sizes, gene detection, sample correlation, outlier detection, CPM normalization.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, QC, count-matrix, library-size, gene-detection, sample-correlation, CPM]
requires: [numpy, pandas, matplotlib, scipy]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "📊"
    trigger_keywords: [bulk QC, library size, count matrix, sample quality, gene detection, RNA-seq quality, count QC]
---

# Bulk RNA-seq Count Matrix QC

Quality control assessment of bulk RNA-seq count matrices. Computes library sizes, gene detection rates, sample-to-sample correlations (log-CPM Pearson), outlier detection, and CPM normalization.

## Core Capabilities

- Compute per-sample library sizes and gene detection rates
- Log-CPM Pearson correlation heatmap with automatic outlier flagging (MAD-based)
- CPM normalization output for downstream analysis
- Expression density plots for cross-sample comparison
- Auto-detect sample group labels from naming conventions

## CLI Reference

```bash
python omicsclaw.py run bulkrna-qc --demo
python omicsclaw.py run bulkrna-qc --input <counts.csv> --output <dir>
python bulkrna_qc.py --input counts.csv --output results/
python bulkrna_qc.py --demo --output /tmp/qc_demo
```

## Why This Exists

- **Without it**: Researchers manually inspect count matrices, compute library sizes in R/Python, generate correlation heatmaps, and visually scan for outlier samples — each step requiring separate scripts and ad-hoc thresholds.
- **With it**: A single Python command runs the full QC pipeline — library sizes, gene detection, log-CPM correlation, outlier flagging, CPM export — and produces publication-ready figures and a structured report.
- **Why OmicsClaw**: Integrates best-practice QC metrics (log-CPM correlation, MAD-based outlier detection) into the OmicsClaw reporting framework with auto-generated demo data for testing.

## Algorithm / Methodology

### Library Size Analysis
- Raw counts per sample are summed to compute library size
- Coefficient of variation (CV) across samples quantifies library size imbalance

### Gene Detection
- Genes detected in each sample (count > 0) are counted
- Distribution shows data sparsity patterns

### Sample Correlation
- Pearson correlation is computed on log2(CPM + 1) transformed data
- Using log-CPM rather than raw counts avoids domination by highly-expressed genes

### Outlier Detection
- Mean inter-sample correlation per sample is compared against the cohort median
- Samples below `median − 2 × MAD × 1.4826` are flagged as potential outliers

### CPM Normalization
- Counts Per Million: `CPM_ij = count_ij / library_size_j × 10^6`

## Input Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Count matrix | `.csv` | Genes as rows, samples as columns; first column is gene identifiers |

## Workflow

1. **Load**: Read a genes-by-samples raw count matrix (CSV).
2. **Library sizes**: Sum counts per sample, compute mean, median, and CV.
3. **Gene detection**: Count samples detecting each gene (count >0).
4. **CPM normalize**: Compute Counts Per Million for downstream use.
5. **Correlate**: Pearson correlation on log2(CPM+1) values.
6. **Outlier detection**: Flag samples with low mean correlation via MAD threshold.
7. **Visualize**: Generate library size bar chart, gene detection histogram, correlation heatmap, and expression density plot.
8. **Report**: Write markdown report, result.json, tables (sample stats, CPM), and reproducibility script.

## Example Queries

- "Check the quality of my bulk RNA-seq count matrix"
- "Are there any outlier samples in my data?"
- "Generate a sample correlation heatmap"
- "Normalize my counts to CPM"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── library_sizes.png
│   ├── gene_detection.png
│   ├── sample_correlation.png
│   └── expression_density.png
├── tables/
│   ├── sample_stats.csv
│   └── cpm_normalized.csv
└── reproducibility/
    └── commands.sh
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | — | Path to count matrix CSV (genes x samples) |
| `--output` | — | Output directory (required) |
| `--demo` | — | Run with bundled/auto-generated demo data |

## Safety

- **Local-first**: All processing runs locally; no data is uploaded to external services.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.
- **Audit trail**: Parameters, sample metadata, and input checksums are recorded in result.json.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked when user intent matches count matrix QC, library size, or sample quality keywords.

**Chaining partners**:
- `bulkrna-de` — Downstream: differential expression on QC-verified data
- `bulkrna-coexpression` — Downstream: co-expression network analysis
- `bulkrna-deconvolution` — Downstream: cell type deconvolution

## Version Compatibility

Reference examples tested with: scipy 1.11+, pandas 2.0+, numpy 1.24+, matplotlib 3.7+

## Dependencies

**Required**: numpy, pandas, scipy, matplotlib

## Related Skills

- `bulkrna-read-qc` — Upstream: FASTQ quality assessment
- `bulkrna-read-alignment` — Upstream: alignment statistics
- `bulkrna-de` — Downstream: differential expression analysis
- `bulkrna-coexpression` — Downstream: co-expression network analysis
- `bulkrna-deconvolution` — Downstream: cell type deconvolution
