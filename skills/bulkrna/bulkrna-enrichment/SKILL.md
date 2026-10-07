---
name: bulkrna-enrichment
description: Load when running pathway / GO term enrichment on a bulk RNA-seq DE result list. Skip when
  the input is single-cell (use sc-enrichment); the input is spatial (use spatial-enrichment); metabolite
  pathways (use metabolomics-pathway-enrichment).
trigger: bulk enrichment, pathway analysis, GSEA, ORA, GO enrichment, KEGG, bulk pathway
tags:
- bulkrna
- enrichment
- GSEA
- ORA
- GO
- KEGG
- Reactome
- pathway
---

# Bulk pathway enrichment

## Purpose

Test differential-expression results against explicit pathway gene sets. ORA uses the union of those sets as its background; GSEA ranks all input genes. Gene identifiers must use the same namespace. R adapters are not implemented.

## Inputs & Outputs

CLI input is a CSV with `gene`, `log2FoldChange`, `pvalue`, `padj`; `--gene-set-file` is a JSON mapping from pathway names to gene lists. The library accepts the table and mapping directly. CLI writes `tables/enrichment_results.csv`, `tables/enrichment_significant.csv`, report/result files and method-dependent figures.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `enrich(de_results, *, gene_sets, method='ora', padj_cutoff=0.05, lfc_cutoff=1.0, random_state=42)`

Test pathway enrichment without choosing a reference database.

:param de_results: DataFrame with gene, log2FoldChange, pvalue and padj.
:param gene_sets: Nonempty mapping from pathway names to unique gene lists.
:param method: CLI default ora; gsea runs GSEApy prerank.
:param padj_cutoff: CLI significance threshold, default 0.05.
:param lfc_cutoff: Strict absolute fold-change threshold, default 1.0.
:param random_state: Local permutation seed, legacy default 42.
:returns: Enrichment DataFrame with execution diagnostics in attrs.
:raises ValueError: Missing reference, invalid values or unsupported method.

### `run_info(result, *, keep=True)`

Read tested terms, pathway universe and requested/executed methods.

:param result: DataFrame returned by enrich.
:param keep: Default True; False removes diagnostic attrs.
:returns: Diagnostic dictionary; empty after removal.

### `enrichment_figure(result)`

Plot pathway adjusted significance without saving it.

:param result: Enrichment DataFrame with term and padj columns.
:returns: matplotlib Figure.
:raises KeyError: Required columns are missing.

<!-- api:end -->

## Key CLI

```bash
python skills/bulkrna/bulkrna-enrichment/bulkrna_enrichment.py --demo --output /tmp/bulkrna-enrichment
python skills/bulkrna/bulkrna-enrichment/bulkrna_enrichment.py --input de.csv --gene-set-file pathways.json --output results/enrichment --method ora
```

## Gotchas

- `run_info(result)['background_genes']` is the pathway-union background, not all measured genes. Choose reference sets accordingly.
- `run_info(result)['executed_method']` and `fallback_reason` disclose fallback calculations. The built-in GSEA fallback is a mean-rank permutation test, not GSEA; fallback emits a warning.
- `tables/enrichment_results.csv` may be empty when no terms overlap. Demo pathways are available only with `--demo`; real input requires an explicit reference.
- `run_info(result)['method_used']` distinguishes GSEApy and built-in calculations. The legacy `ora_r` and `gsea_r` flags now reject an unimplemented backend rather than silently changing it.

## Dependencies

`numpy`, `pandas`, `scipy`, `matplotlib`, `gseapy`
