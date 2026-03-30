---
name: bulkrna-de
description: >-
  Differential expression analysis via PyDESeq2 with Welch's t-test fallback — volcano plots, MA plots, p-value diagnostics.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, differential-expression, DESeq2, volcano, MA-plot, fold-change]
requires: [numpy, pandas, matplotlib, scipy]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🔬"
    trigger_keywords: [differential expression, DE analysis, DESeq2, volcano plot, fold change, DEGs, bulk DE]
    allowed_extra_flags:
      - "--control-prefix"
      - "--lfc-cutoff"
      - "--method"
      - "--padj-cutoff"
      - "--treat-prefix"
    legacy_aliases: [bulk-de]
    saves_h5ad: false
---

# Bulk RNA-seq Differential Expression

Differential expression analysis for bulk RNA-seq count matrices. Primary engine is PyDESeq2 (Python implementation of the DESeq2 model); falls back to Welch's t-test with log2FC and Benjamini-Hochberg FDR correction when PyDESeq2 is not installed.

## Core Capabilities

- Full DESeq2-style negative binomial GLM via PyDESeq2, or Welch's t-test fallback
- Produces columns consistent with DESeq2 output: gene, baseMean, log2FoldChange, lfcSE, stat, pvalue, padj
- Volcano plot with top gene labels and MA plot with threshold lines
- P-value distribution histogram for diagnostic assessment
- Automatic sample group detection from column name prefixes
- Benjamini-Hochberg FDR correction with proper NaN handling

## CLI Reference

```bash
python omicsclaw.py run bulkrna-de --demo
python omicsclaw.py run bulkrna-de --input <counts.csv> --output <dir>
python bulkrna_de.py --input counts.csv --output results/
python bulkrna_de.py --demo --output /tmp/de_demo
python bulkrna_de.py --input counts.csv --output results/ --method ttest --ctrl-prefix ctrl --treat-prefix treat
python bulkrna_de.py --input counts.csv --output results/ --padj-cutoff 0.01 --lfc-cutoff 1.5
```

## Why This Exists

- **Without it**: Researchers must install R and DESeq2, write design formulas, handle normalization, shrinkage, and multiple testing correction manually, then create separate visualization scripts.
- **With it**: A single Python command runs the full DE pipeline — from raw counts to filtered DEG tables, volcano plots, MA plots, and p-value diagnostic histograms.
- **Why OmicsClaw**: Provides a pure-Python DE workflow via PyDESeq2 with graceful fallback to t-test, integrated into the OmicsClaw reporting framework.

## Algorithm / Methodology

### PyDESeq2 (Primary)
1. Construct `DeseqDataSet` from count matrix and sample metadata
2. Estimate size factors (median-of-ratios normalization)
3. Estimate dispersions (Cox-Reid profile-adjusted maximum likelihood)
4. Fit negative binomial GLM and perform Wald test
5. Apply Benjamini-Hochberg FDR correction

### Welch's t-test (Fallback)
1. Compute log2 fold change: `log2(mean_treat + 1) - log2(mean_ctrl + 1)`
2. Estimate standard error via delta method approximation
3. Welch's t-test (unequal variance) per gene
4. Benjamini-Hochberg FDR with NaN-safe handling

### Key Parameters
- **padj_cutoff**: Adjusted p-value threshold (default: 0.05)
- **lfc_cutoff**: Absolute log2FC threshold (default: 1.0)
- **min_count**: Gene pre-filtering threshold — genes with total counts < 10 across all samples are removed before testing (improves statistical power and PyDESeq2 performance)

## Design Validation

Before running DE, the system validates:
- **Replication**: At least 2 replicates per condition required (>= 3 recommended)
- **Gene pre-filtering**: Removes genes with total counts < 10 (reduces multiple testing burden, improves dispersion estimation)
- **Sample counts**: Logs per-condition sample counts for transparency

## LFC Shrinkage Guidance

| Method | Purpose | When to use |
|--------|---------|-------------|
| Unshrunk (default) | Hypothesis testing | Statistical significance thresholds (padj < 0.05) |
| apeglm | Visualization/ranking | Shrinks large LFCs of low-expression genes; best for MA/volcano plots |
| ashr | Adaptive shrinkage | When some genes have very large true effects |

> **Note**: Current output uses unshrunk LFCs (suitable for hypothesis testing). For visualization/ranking, consider applying shrinkage externally.

## Transformation Guidance

| Transform | When to use | Speed |
|-----------|-------------|-------|
| VST (variance stabilizing) | > 30 samples, PCA/clustering | Fast |
| rlog (regularized log) | < 30 samples, PCA/heatmaps | Slow |
| log2(count + 1) | Quick exploration | Instant |

> **Important**: Transformations are for visualization only — always use raw counts for DE testing.

## Input Formats

| Format | Extension | Required Columns | Example |
|--------|-----------|-----------------|---------|
| Count matrix | `.csv` | Gene identifier column + sample count columns | `gene,ctrl_1,ctrl_2,ctrl_3,treat_1,treat_2,treat_3` |

## Workflow

1. **Load**: Read a genes-by-samples raw count matrix (CSV with first column as gene names).
2. **Group**: Automatically partition sample columns into control and treatment groups by prefix.
3. **Analyse**: Run PyDESeq2 negative binomial GLM, or Welch's t-test if PyDESeq2 is unavailable.
4. **Filter**: Identify significant DEGs by padj and |log2FC| thresholds.
5. **Visualize**: Generate volcano plot (with top gene labels), MA plot, DE bar chart, and p-value histogram.
6. **Report**: Write markdown report, result.json, DE results table, and reproducibility script.

## Example Queries

- "Find differentially expressed genes between control and treatment"
- "Run DESeq2 on my bulk RNA-seq count matrix"
- "Generate a volcano plot of my DE results"
- "Which genes are significantly upregulated?"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── volcano_plot.png
│   ├── ma_plot.png
│   ├── de_barplot.png
│   └── pvalue_histogram.png
├── tables/
│   ├── de_results.csv
│   └── de_significant.csv
└── reproducibility/
    └── commands.sh
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `pydeseq2` | DE method: `pydeseq2` or `ttest` |
| `--ctrl-prefix` | `ctrl` | Column name prefix for control samples |
| `--treat-prefix` | `treat` | Column name prefix for treatment samples |
| `--padj-cutoff` | `0.05` | Adjusted p-value significance threshold |
| `--lfc-cutoff` | `1.0` | Absolute log2 fold-change threshold |

## Safety

- **Local-first**: All processing runs locally; no data is uploaded to external services.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.
- **Audit trail**: Parameters, method used (including fallback events), and input checksums are recorded in result.json.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked when user intent matches differential expression, DESeq2, volcano plot, or fold change keywords.

**Chaining partners**:
- `bulkrna-qc` — Upstream: count matrix QC
- `bulkrna-enrichment` — Downstream: pathway enrichment of DEG lists
- `bulkrna-coexpression` — Parallel: co-expression analysis
- `bulkrna-splicing` — Parallel: gene-level DE complements exon-level splicing

## Version Compatibility

Reference examples tested with: scipy 1.11+, pandas 2.0+, numpy 1.24+, matplotlib 3.7+, pydeseq2 0.4+

## Dependencies

**Required**: numpy, pandas, scipy, matplotlib
**Optional**: pydeseq2 (recommended; provides full DESeq2 negative binomial GLM)

## Citations

- [DESeq2](https://doi.org/10.1186/s13059-014-0550-8) — Love et al., Genome Biology 2014
- [PyDESeq2](https://doi.org/10.1093/bioinformatics/btad547) — Muzellec et al., Bioinformatics 2023
- [Benjamini-Hochberg](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) — Benjamini & Hochberg, JRSSB 1995

## Related Skills

- `bulkrna-qc` — Count matrix QC upstream
- `bulkrna-enrichment` — Pathway enrichment of DE gene lists downstream
- `bulkrna-coexpression` — Co-expression network analysis
- `bulkrna-splicing` — Alternative splicing analysis
