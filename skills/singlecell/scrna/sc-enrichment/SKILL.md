---
name: sc-enrichment
description: Load when running bulk-style pathway enrichment (ORA / GSEA / GSEA-R / GSVA-R) on a per-group ranked DE / marker list against a gene-set library. Skip when computing per-cell pathway scores in-place (use sc-pathway-scoring) or for de-novo gene-program discovery (use sc-gene-programs).
version: 0.4.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- enrichment
- gsea
- ora
- gsva
- decoupler
- pathway-enrichment
requires:
- anndata
- scanpy
- numpy
- pandas
---

# sc-enrichment

## When to use

The user has a clustered / labelled scRNA AnnData and wants per-group
pathway enrichment from a marker / DE ranking against a gene-set
library. Four methods × two engines:

- `ora` (default) — over-representation analysis on the top-K markers
  per group (`--ora-padj-cutoff` / `--ora-log2fc-cutoff` /
  `--ora-max-genes`).
- `gsea` — pre-ranked GSEA using the ranking metric from
  `sc.tl.rank_genes_groups` (`--gsea-ranking-metric`,
  `--gsea-min-size` / `--gsea-max-size`, etc.).
- `gsea_r` — R-backed `fgsea`/`clusterProfiler`-style GSEA.
- `gsva_r` — GSVA per-cell or per-group score matrix (R only;
  `--groupby` required).

Engine selection (`--engine auto/python/r`) is independent — `auto`
picks the right engine for the method.

For per-cell scoring (no rankings, just gene sets) use
`sc-pathway-scoring`. For de-novo factorisation (no gene sets) use
`sc-gene-programs`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Clustered / labelled AnnData | `.h5ad` | yes (unless `--demo`) |
| Gene sets | `.gmt` (`--gene-sets`) **OR** library alias (`--gene-set-db hallmark`/`kegg`/...) **OR** marker source (`--gene-set-from-markers`) | yes (unless `--demo`) |
| Group column | `--groupby` (auto-resolves if unset) | optional (required for `gsva_r`) |

| Output | Path | Notes |
|---|---|---|
| AnnData | `processed.h5ad` | preserved with contract metadata |
| All terms | `tables/enrichment_results.csv` | per-group × term, score / pvalue / pvalue_adj |
| Significant subset | `tables/enrichment_significant.csv` | filtered at `--fdr-threshold` |
| Group summary | `tables/group_summary.csv` | counts + top term per group |
| Ranking used | `tables/ranking_input.csv` | the gene ranking actually fed to the method |
| Top terms | `tables/top_terms.csv` | top-`--top-terms` for figures |
| GSEA running scores | `tables/gsea_running_scores.csv` | when method == `gsea` (Python) |
| GSVA R scores | `tables/gsva_r_scores.csv` | when method == `gsva_r` |
| Figures | `top_terms_bar.png`, `group_term_dotplot.png`, `group_enrichment_summary.png`, `gsea_running_scores.png`, `gsva_r_heatmap.png` (gsva_r only) | rendered via `_lib/viz/stat_enrichment.py` |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or build a demo.
2. Resolve gene-set source: GMT path / library alias / `--gene-set-from-markers` (treats another skill's marker output as a gene-set library).
3. Resolve `--groupby`; for `ora` / `gsea` build per-group rankings from `sc.tl.rank_genes_groups` with `--ranking-method` (Wilcoxon / t-test / logreg).
4. Filter rankings by method-specific cutoffs (`--ora-*` for ORA, `--gsea-*` for GSEA).
5. Run enrichment via Python or R engine; standardise the result table to a common schema (`group`, `term`, `gene_set`, `source`, `library_mode`, `engine`, `method_used`, `score`, `pvalue`, `pvalue_adj`, ...).
6. Build group-summary + top-terms tables; render figures.
7. Save tables, figures, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **`--input` is `ValueError`, not `parser.error` here.** `sc_enrichment.py:280` raises `ValueError("--input is required unless `--demo` is used.")` (more standard than sibling skills that use `parser.error` / `SystemExit`). Once `--input` is given, `:284` raises `FileNotFoundError(f"Input path not found: {path}")` for a missing path.
- **One of `--gene-sets` / `--gene-set-db` / `--gene-set-from-markers` is required.** `sc_enrichment.py:407` raises `ValueError("Provide either `--gene-sets <local.gmt>` or `--gene-set-db <hallmark|kegg|...>`.")` when none of the three are supplied. Library aliases include `hallmark`, `kegg`, `reactome`, `go_bp`; arbitrary strings are passed through to the EnrichR library API.
- **Marker-as-gene-set requires specific columns.** `sc_enrichment.py:367` raises `FileNotFoundError(f"...")` for a missing `--gene-set-from-markers` path; `:372` raises `ValueError("Marker gene-set source must contain `group` and `names` columns.")` when the file is malformed (e.g., didn't come from `sc-markers` / `sc-de`).
- **`gsva_r` requires `--groupby`.** `sc_enrichment.py:1212` raises `ValueError("gsva_r needs a groupby column. Use --groupby <column>.")`. The other 3 methods can auto-resolve `--groupby` from `leiden` / `louvain` / `cell_type` if unset.
- **R-engine paths need bundled R scripts present.** `sc_enrichment.py:620` raises `FileNotFoundError(f"R script not found: {r_script}")` for `gsea_r`; `:734` raises the same shape for `gsva_r`. These are bundled with the skill — only fails if the install is incomplete.
- **Zero overlap between gene sets and the dataset is a hard fail.** `sc_enrichment.py:1313` raises `ValueError("No overlapping genes remained after aligning the selected gene sets to the dataset gene universe.")` after the gene-symbol mapping step. Run `sc-standardize-input` upstream if symbols don't match.
- **`result.json["method_used"]` differs from `--method` when engine routes to R.** `sc_enrichment.py:578` / `:599` / `:698` set `method_used` to the *normalised* form (`ora` / `gsea` / `gsea_r`). With `--engine auto` and `--method gsea`, the run may execute `gsea_r` if the Python engine is unavailable — always inspect `method_used`, not `--method`.

## Key CLI

```bash
# Demo (built-in markers + Hallmark gene sets)
python omicsclaw.py run sc-enrichment --demo --output /tmp/sc_enrich_demo

# ORA on Hallmark, auto group-by
python omicsclaw.py run sc-enrichment \
  --input clustered.h5ad --output results/ \
  --method ora --gene-set-db hallmark

# GSEA pre-ranked from Wilcoxon scores
python omicsclaw.py run sc-enrichment \
  --input clustered.h5ad --output results/ \
  --method gsea --gene-set-db kegg \
  --groupby cell_type --gsea-ranking-metric scores

# Use existing markers from sc-markers as gene-set library
python omicsclaw.py run sc-enrichment \
  --input clustered.h5ad --output results/ \
  --method ora --gene-set-from-markers prev_run/tables/markers_all.csv \
  --marker-group "T cell,B cell" --marker-top-n 50

# GSVA-R (group-aware)
python omicsclaw.py run sc-enrichment \
  --input clustered.h5ad --output results/ \
  --method gsva_r --groupby cell_type --gene-set-db hallmark
```

## See also

- `references/parameters.md` — every CLI flag, library aliases, ORA/GSEA tunables
- `references/methodology.md` — ORA vs GSEA vs GSVA; ranking-metric guide
- `references/output_contract.md` — `enrichment_results.csv` column schema; per-method differences
- Adjacent skills: `sc-markers` / `sc-de` (upstream — produce the rankings consumed here; can also be re-used as gene sets via `--gene-set-from-markers`), `sc-pathway-scoring` (parallel — per-cell scoring against gene sets, NOT per-group enrichment), `sc-gene-programs` (parallel — de-novo factorisation, NOT supervised enrichment), `sc-cell-annotation` (upstream — produces meaningful biological labels for `--groupby`)
