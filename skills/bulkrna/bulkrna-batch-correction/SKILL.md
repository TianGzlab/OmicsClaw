---
name: bulkrna-batch-correction
description: >-
  Batch effect correction for multi-cohort bulk RNA-seq data using ComBat, with PCA-based
  visualization before and after correction.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, batch-correction, ComBat, harmonization, batch-effect]
requires: [numpy, pandas, matplotlib, scipy]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🔧"
    trigger_keywords: [batch correction, ComBat, batch effect, harmonize, multi-cohort,
      batch removal]
    allowed_extra_flags:
    - "--batch-info"
    - "--mode"
    legacy_aliases: [bulk-combat]
    saves_h5ad: false
    script: bulkrna_batch_correction.py
    param_hints: {}
    requires_preprocessed: false
---

# Bulk RNA-seq Batch Effect Correction

Remove batch effects from multi-cohort bulk RNA-seq expression matrices using the ComBat algorithm (parametric and non-parametric modes), with PCA-based visualization and quantitative assessment.

## Core Capabilities

- Parametric and non-parametric ComBat batch correction
- Built-in empirical Bayes implementation (no external R dependency)
- PCA visualization before and after correction with batch coloring
- Quantitative batch-effect metrics: silhouette score, kBET-like metric
- Export corrected expression matrices in CSV format
- Automatic batch detection from sample naming conventions

## Why This Exists

- **Without it**: Users must install R, load the `sva` package, manually create model matrices, run `ComBat()`, and export corrected data back to Python — a multi-step cross-language workflow.
- **With it**: A single Python command performs batch correction on CSV expression matrices and generates before/after PCA plots with quantitative batch-mixing metrics.
- **Why OmicsClaw**: Pure Python ComBat implementation integrated into the OmicsClaw reporting framework, with automated batch-effect assessment.

## Algorithm / Methodology

### ComBat (Johnson et al., 2007)
1. Standardize expression data by gene (subtract mean, divide by std)
2. Estimate batch-specific location and scale parameters
3. Apply empirical Bayes shrinkage to batch parameter estimates
4. Adjust expression values to remove batch effects while preserving biological variation

### Parametric vs Non-parametric
- **Parametric** (default): Assumes normal distribution for batch effects; faster
- **Non-parametric**: Uses kernel density estimation; more robust for non-normal batch effects

### PCA Assessment
- PCA on log2(CPM+1) transformed data, colored by batch label
- Silhouette score: measures how well batches cluster (lower = better mixing after correction)

## Input Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Expression matrix | `.csv` | Genes as rows, samples as columns; first column is gene identifiers |
| Batch metadata | `.csv` | Two columns: `sample` and `batch` (or auto-detected from sample names) |

## CLI Reference

```bash
python omicsclaw.py run bulkrna-batch-correction --demo
python omicsclaw.py run bulkrna-batch-correction --input expr.csv --batch-info batches.csv --output results/
python bulkrna_batch_correction.py --input expr.csv --batch-info batches.csv --output results/
python bulkrna_batch_correction.py --demo --output /tmp/batch_demo
```

## Workflow

1. **Load**: Read expression matrix and batch metadata (or auto-detect batches from sample names).
2. **Assess**: PCA and batch-mixing metrics on uncorrected data.
3. **Correct**: Apply ComBat (parametric or non-parametric mode).
4. **Validate**: PCA and batch-mixing metrics on corrected data.
5. **Compare**: Side-by-side before/after PCA visualization.
6. **Export**: Corrected expression matrix, figures, and report.

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── pca_before_correction.png
│   ├── pca_after_correction.png
│   └── batch_assessment.png
├── tables/
│   ├── corrected_expression.csv
│   └── batch_metrics.csv
└── reproducibility/
    └── commands.sh
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | — | Path to expression matrix CSV |
| `--batch-info` | — | Path to batch metadata CSV (sample, batch columns) |
| `--output` | — | Output directory |
| `--mode` | `parametric` | ComBat mode: `parametric` or `non-parametric` |
| `--demo` | — | Run with auto-generated demo data |

## Safety

- **Local-first**: All processing runs locally; no data is uploaded.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.
- **Audit trail**: Parameters and batch assignments are recorded in result.json.

## Integration with Orchestrator

**Trigger conditions**: Automatically invoked when user intent matches batch correction, ComBat, harmonization keywords.

**Chaining partners**:
- `bulkrna-qc` — Upstream: count matrix QC
- `bulkrna-de` — Downstream: DE analysis on corrected data
- `bulkrna-coexpression` — Downstream: co-expression on corrected data

## Citations

- [ComBat](https://doi.org/10.1093/biostatistics/kxj037) — Johnson et al., Biostatistics 2007

## Dependencies

**Required**: numpy, pandas, scipy, matplotlib

## Related Skills

- `bulkrna-qc` — Count matrix QC upstream
- `bulkrna-de` — Differential expression on corrected data
