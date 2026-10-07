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

# Bulk differential expression

## Purpose

Compare two prefix-selected groups in a raw count matrix. The default backend is R DESeq2; `--method ttest` selects Welch tests. The R bridge applies apeglm or ashr shrinkage when installed, otherwise raw estimates. This is not a single-cell or splicing analysis.

## Inputs & Outputs

CLI input is a gene-first CSV. The library takes a gene-indexed DataFrame. Both require nonnegative integer counts. Outputs include `tables/de_results.csv`, `tables/de_significant.csv`, four diagnostic figures, `report.md` and `result.json`; DESeq2 intermediate tables are backend-dependent.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `differential_expression(counts, *, method='deseq2', control_prefix='ctrl', treat_prefix='treat', padj_cutoff=0.05, lfc_cutoff=1.0, min_count=10)`

Compare treatment against control without changing the count matrix.

:param counts: Gene-indexed DataFrame of nonnegative integer raw counts.
:param method: CLI default deseq2 (R); ttest selects Welch tests.
:param control_prefix: CLI default ctrl selects control columns.
:param treat_prefix: CLI default treat selects treatment columns.
:param padj_cutoff: CLI default 0.05; significance requires a smaller adjusted p.
:param lfc_cutoff: CLI default 1.0; absolute log2 effect must exceed it.
:param min_count: Legacy filtering default 10 for total counts across selected samples.
:returns: DE DataFrame with effect estimates, p values and run diagnostics in attrs.
:raises ValueError: Counts, method, groups or thresholds are invalid.
:raises ImportError: R DESeq2 is missing; use install_skill_deps for DESeq2.

### `run_info(result, *, keep=True)`

Read filtering, group and executed-method diagnostics.

:param result: DataFrame returned by differential_expression.
:param keep: Default True; False removes diagnostics from attrs.
:returns: Diagnostic dictionary, empty after removal.

### `volcano_figure(result)`

Plot reported log2 effects and adjusted significance.

:param result: DE DataFrame with log2FoldChange and padj.
:returns: A matplotlib Figure without saving files.
:raises KeyError: Required columns are absent.

<!-- api:end -->

## Key CLI

```bash
python skills/bulkrna/bulkrna-de/bulkrna_de.py --demo --output /tmp/bulkrna-de
python skills/bulkrna/bulkrna-de/bulkrna_de.py --input counts.csv --output results/de --method ttest
```

## Gotchas

- `run_info(result)['method_used']` identifies the executed method. Missing DESeq2 raises an installation hint; a failed R fit can fall back to Welch with a warning and `fallback_reason`.
- `run_info(result)['lfc_note']` distinguishes Welch effects from the R bridge's package-dependent shrinkage. Welch tests are not a substitute for biological replication.
- `run_info(result)['n_tested']` counts genes after the default total-count filter of 10. Unmatched sample prefixes do not enter the comparison.

## Dependencies

`numpy`, `pandas`, `scipy`, `matplotlib`, `DESeq2`
