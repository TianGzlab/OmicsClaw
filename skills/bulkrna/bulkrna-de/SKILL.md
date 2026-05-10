---
name: bulkrna-de
description: Load when comparing gene expression between two conditions in bulk RNA-seq count data. Skip when the data is single-cell (use sc-de) or spatial (use spatial-de), or when you need exon-level alternative splicing (use bulkrna-splicing).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- differential-expression
- DESeq2
- volcano
- MA-plot
- fold-change
requires:
- numpy
- pandas
- matplotlib
- scipy
---

# bulkrna-de

## When to use

The user has a bulk RNA-seq count matrix (genes × samples) and wants to know
which genes change between two groups (control vs treatment, tumour vs normal,
etc.).  PyDESeq2 is preferred when ≥2 replicates per condition exist; Welch's
t-test is the fallback for the single-replicate / no-PyDESeq2 case.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Count matrix | `.csv` (gene id col + sample count cols) | yes |

| Output | Path | Notes |
|---|---|---|
| DE results | `tables/de_results.csv` | DESeq2-style columns (gene, baseMean, log2FoldChange, lfcSE, stat, pvalue, padj) |
| Significant DEGs | `tables/de_significant.csv` | filtered by padj + |log2FC| |
| Volcano | `figures/volcano_plot.png` | top genes labelled |
| MA plot | `figures/ma_plot.png` | threshold lines drawn |
| p-value diagnostic | `figures/pvalue_histogram.png` | check for inflation |
| Report | `report.md` + `result.json` | always written |

## Flow

1. Load genes × samples raw count matrix.
2. Auto-partition columns into control / treatment by name prefix.
3. Pre-filter genes with total counts < 10 across all samples.
4. Run PyDESeq2 (negative binomial GLM + Wald test) — fall back to Welch's t-test if PyDESeq2 missing or < 2 replicates per condition.
5. Apply Benjamini–Hochberg FDR correction.
6. Filter DEGs by `--padj-cutoff` and `--lfc-cutoff`.
7. Render volcano / MA / p-value histogram and emit report.

## Gotchas

- **PyDESeq2 silently falls back to Welch's t-test** when fewer than 2 replicates per condition are detected or `pydeseq2` is not importable.  Check `result.json["method_used"]` to confirm which engine actually ran — the volcano-plot title alone does not surface the fallback.
- **LFCs are unshrunk by design.** Suitable for hypothesis testing (padj thresholds), but for ranking / visualisation that emphasises high-confidence effects, apply apeglm or ashr shrinkage *outside* this skill.
- **VST / rlog transformations are visualisation-only.** Do not feed transformed counts back into this skill — DE testing always wants raw integer counts.
- **Sample group detection is prefix-based.** Columns must start with `--control-prefix` (default `ctrl`) or `--treat-prefix` (default `treat`); columns matching neither prefix are silently dropped.
- **Pre-filter removes low-count genes** (total < 10).  This improves dispersion estimation but means the input gene count is not the testing gene count — `result.json["n_tested"]` is authoritative.

## Key CLI

```bash
# Demo run (synthetic 200-gene × 12-sample dataset)
python omicsclaw.py run bulkrna-de --demo

# Realistic run with custom prefixes and stricter cutoffs
python omicsclaw.py run bulkrna-de \
  --input counts.csv --output results/ \
  --control-prefix wt --treat-prefix ko \
  --padj-cutoff 0.01 --lfc-cutoff 1.5
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — PyDESeq2 vs t-test, design validation, LFC shrinkage and transformation guidance
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-qc` (upstream count-matrix QC), `bulkrna-enrichment` (downstream pathway enrichment of DEG lists), `bulkrna-coexpression` (parallel WGCNA), `bulkrna-splicing` (exon-level alternative splicing)
