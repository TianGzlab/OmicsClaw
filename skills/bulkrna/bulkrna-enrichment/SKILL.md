---
name: bulkrna-enrichment
description: Load when running pathway / GO term enrichment on a bulk RNA-seq DE result list. Skip if the input is single-cell (use sc-enrichment), spatial (use spatial-enrichment), or for metabolite pathways (use metabolomics-pathway-enrichment).
version: 0.3.0
author: OmicsClaw
license: MIT
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

# bulkrna-enrichment

## When to use

Run after `bulkrna-de` to ask "which biological pathways are enriched
in the DEG list?".  Two modes: ORA (over-representation analysis on a
significance-filtered gene list) and pre-ranked GSEA (full ranked
list, no threshold needed).  Backed by GSEApy with R clusterProfiler
and a built-in hypergeometric implementation as fallbacks.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| DE results | `.csv` (gene + log2FoldChange + padj cols) | yes (or `--demo`) |
| Custom gene set | `--gene-set-file` GMT/JSON | optional |

| Output | Path | Notes |
|---|---|---|
| Enrichment table | `tables/enrichment_results.csv` | per-term padj, NES, leading-edge genes |
| Top terms barplot | `figures/enrichment_barplot.png` | top N by padj |
| Dotplot | `figures/enrichment_dotplot.png` | size = gene count, colour = padj |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load DE table; pick a ranking metric (log2FoldChange, signed -log10 padj, etc.).  Falls back to `log2FoldChange` with a warning at `bulkrna_enrichment.py:67` if the heuristic finds no preferred metric.
2. Resolve `--method`: ORA, GSEA, or auto.  Hard-fails at `:370` for unknown methods.
3. Try R clusterProfiler first; on import failure, fall back to GSEApy (`:379`).
4. On GSEApy failure, fall back to the built-in hypergeometric implementation (`:436` ORA path, `:479` GSEA path).
5. Render barplot + dotplot; emit enrichment table + report.

## Gotchas

- **Three-tier silent fallback chain.**  R clusterProfiler → GSEApy → built-in.  Each fall is `logger.warning`-only (`bulkrna_enrichment.py:379, :436, :479`); the chosen backend is in `result.json["method_used"]`.  Built-in is the least feature-rich (no permutation-based GSEA p-values) — verify which engine actually ran before claiming a particular method.
- **Ranking-metric auto-pick is heuristic and not surfaced in `result.json`.**  `:67` warns when it falls back to `log2FoldChange`, but if your DE table uses a non-standard column name (e.g. `lfc` instead of `log2FoldChange`), the heuristic may pick the wrong column without complaint.  The chosen metric is logged at INFO (`:450`) but does NOT make it into the summary dict (which carries only `n_input_genes`, `n_significant`, `method_used`, `n_terms_tested`, `n_enriched_terms`, `enrichment_df`).  Grep the run's stderr for "Using gseapy for pre-ranked GSEA (metric: ...)" to confirm.
- **`--padj-cutoff` and `--lfc-cutoff` only apply to ORA.**  Pre-ranked GSEA uses the full ranked list and ignores both flags — passing them on a GSEA run silently does nothing.  This is correct GSEA behaviour, but easy to mistake for a bug.
- **No DEGs above thresholds → silent empty plots.**  `:516` and `:525` warn ("No enrichment results to plot" / "No terms with valid padj") and skip plotting; the run still exits 0 with empty figures and an empty `tables/enrichment_results.csv`.  Loosen thresholds or pre-filter the input if your DE list is sparse.

## Key CLI

```bash
python omicsclaw.py run bulkrna-enrichment --demo
python omicsclaw.py run bulkrna-enrichment \
  --input de_results.csv --output results/ --method ora
python omicsclaw.py run bulkrna-enrichment \
  --input de_results.csv --output results/ --method gsea \
  --gene-set-file hallmark.gmt
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — ORA vs GSEA, three-tier engine fallback, ranking-metric selection
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-de` (upstream — DE table input), `bulkrna-ppi-network` (parallel: same DEG list → STRING network), `sc-enrichment` / `spatial-enrichment` (single-cell / spatial siblings), `metabolomics-pathway-enrichment` (metabolite-side sibling)
