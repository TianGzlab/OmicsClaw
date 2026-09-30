---
name: bulkrna-de
description: Load when comparing gene expression between two conditions in bulk RNA-seq count data. Skip
  when the data is single-cell (use sc-de); spatial (use spatial-de); you need exon-level alternative
  splicing (use bulkrna-splicing).
trigger: differential expression, DE analysis, DESeq2, volcano plot, fold change, DEGs, bulk DE
tags:
- bulkrna
- differential-expression
- DESeq2
- volcano
- MA-plot
- fold-change
---

# bulkrna-de

## When to use

The user has a bulk RNA-seq count matrix (genes × samples) and wants to know
which genes change between two groups (control vs treatment, tumour vs normal,
etc.).  PyDESeq2 is preferred when ≥2 replicates per condition exist; Welch's
t-test is the fallback for the single-replicate / no-PyDESeq2 case.

## Inputs & Outputs

**Inputs**

- File types: `.csv`
- Accepts artifact `bulkrna.count_matrix` (`csv`)
- Tabular structure: at least 3 columns

**Outputs**

- `tables/counts.csv`
- `tables/de_results.csv`
- `tables/de_significant.csv`
- `tables/deseq2_results.csv`
- `figures/de_barplot.png`
- `figures/ma_plot.png`
- `figures/pvalue_histogram.png`
- `figures/volcano_plot.png`
- `report.md`
- `result.json`
- Produces artifact `bulkrna.differential_results` as `tables/de_results.csv` (`csv`)

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
python skills/bulkrna/bulkrna-de/bulkrna_de.py --demo --output /tmp/bulkrna-de_demo

# Realistic run with custom prefixes and stricter cutoffs
python skills/bulkrna/bulkrna-de/bulkrna_de.py \
  --input counts.csv --output results/ \
  --control-prefix wt --treat-prefix ko \
  --padj-cutoff 0.01 --lfc-cutoff 1.5
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — PyDESeq2 vs t-test, design validation, LFC shrinkage and transformation guidance
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-qc` (upstream count-matrix QC), `bulkrna-enrichment` (downstream pathway enrichment of DEG lists), `bulkrna-coexpression` (parallel WGCNA), `bulkrna-splicing` (exon-level alternative splicing)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`matplotlib`, `numpy`, `pandas`, `scipy`
