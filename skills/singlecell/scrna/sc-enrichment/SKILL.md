---
name: sc-enrichment
description: Load when running bulk-style pathway enrichment (ORA / GSEA / GSEA-R / GSVA-R) on a per-group
  ranked DE / marker list against a gene-set library. Skip when computing per-cell pathway scores in-place
  (use sc-pathway-scoring); de-novo gene-program discovery (use sc-gene-programs).
trigger: sc enrichment, single-cell enrichment, GO enrichment, KEGG enrichment, GSEA, ORA, pathway enrichment
tags:
- singlecell
- scrna
- enrichment
- gsea
- ora
- gsva
- decoupler
- pathway-enrichment
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

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/cell_metadata.csv`
- `tables/clusterprofiler_results.csv`
- `tables/de_for_gsea_r.csv`
- `tables/de_full.csv`
- `tables/enrichment_results.csv`
- `tables/enrichment_significant.csv`
- `tables/group_expr_for_gsva.csv`
- `tables/group_summary.csv`
- `tables/gsea_input.csv`
- `tables/gsea_r_results.csv`
- `tables/gsea_running_scores.csv`
- `tables/gsva_r_scores.csv`
- `tables/markers_all.csv`
- `tables/ora_input.csv`
- `tables/ranking_input.csv`
- `tables/top_terms.csv`
- `figures/gsva_r_heatmap.png`
- `figures/r_enrichment_bar.png`
- `figures/r_enrichment_dotplot.png`
- `figures/r_enrichment_enrichmap.png`
- `figures/r_enrichment_lollipop.png`
- `figures/r_enrichment_network.png`
- `figures/r_gsea_mountain.png`
- `figures/r_gsea_nes_heatmap.png`
- `analysis_summary.txt`
- `background_genes.txt`
- `processed.h5ad`
- `r_plot_metadata.json`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`)

## Flow

1. Load AnnData (`--input`) or build a demo.
2. Resolve gene-set source: GMT path / library alias / `--gene-set-from-markers` (treats another skill's marker output as a gene-set library).
3. Resolve `--groupby`; for `ora` / `gsea` build per-group rankings from `sc.tl.rank_genes_groups` with `--ranking-method` (Wilcoxon / t-test / logreg).
4. Filter rankings by method-specific cutoffs (`--ora-*` for ORA, `--gsea-*` for GSEA).
5. Run enrichment via Python or R engine; standardise the result table to a common schema (`group`, `term`, `gene_set`, `source`, `library_mode`, `engine`, `method_used`, `score`, `pvalue`, `pvalue_adj`, ...).
6. Build group-summary + top-terms tables; render figures.
7. Save tables, figures, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **`--input` is `ValueError`, not `parser.error` here.** `sc_enrichment.py` raises `ValueError("--input is required unless `--demo` is used.")` (more standard than sibling skills that use `parser.error` / `SystemExit`). Once `--input` is given, `_load_input_context` raises `FileNotFoundError(f"Input path not found: {path}")` for a missing path.
- **One of `--gene-sets` / `--gene-set-db` / `--gene-set-from-markers` is required.** `sc_enrichment.py` raises `ValueError("Provide either `--gene-sets <local.gmt>` or `--gene-set-db <hallmark|kegg|...>`.")` when none of the three are supplied. Library aliases include `hallmark`, `kegg`, `reactome`, `go_bp`; arbitrary strings are passed through to the EnrichR library API.
- **Marker-as-gene-set requires specific columns.** `sc_enrichment.py` raises `FileNotFoundError(f"...")` for a missing `--gene-set-from-markers` path; raises `ValueError("Marker gene-set source must contain `group` and `names` columns.")` when the file is malformed (e.g., didn't come from `sc-markers` / `sc-de`).
- **`gsva_r` requires `--groupby`.** `sc_enrichment.py` raises `ValueError("gsva_r needs a groupby column. Use --groupby <column>.")`. The other 3 methods can auto-resolve `--groupby` from `leiden` / `louvain` / `cell_type` if unset.
- **R-engine paths need bundled R scripts present.** `sc_enrichment.py` raises `FileNotFoundError(f"R script not found: {r_script}")` for `gsea_r`; raises the same shape for `gsva_r`. These are bundled with the skill — only fails if the install is incomplete.
- **Zero overlap between gene sets and the dataset is a hard fail.** `sc_enrichment.py` raises `ValueError("No overlapping genes remained after aligning the selected gene sets to the dataset gene universe.")` after the gene-symbol mapping step. Run `sc-standardize-input` upstream if symbols don't match.
- **`result.json["method_used"]` differs from `--method` when engine routes to R.** `sc_enrichment.py` sets `method_used` to the *normalised* form (`ora` / `gsea` / `gsea_r`). With `--engine auto` and `--method gsea`, the run may execute `gsea_r` if the Python engine is unavailable — always inspect `method_used`, not `--method`.

## Key CLI

```bash
# Demo (built-in markers + Hallmark gene sets)
python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py --demo --output /tmp/sc_enrich_demo

# ORA on Hallmark, auto group-by
python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py \
  --input clustered.h5ad --output results/ \
  --method ora --gene-set-db hallmark

# GSEA pre-ranked from Wilcoxon scores
python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py \
  --input clustered.h5ad --output results/ \
  --method gsea --gene-set-db kegg \
  --groupby cell_type --gsea-ranking-metric scores

# Use existing markers from sc-markers as gene-set library
python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py \
  --input clustered.h5ad --output results/ \
  --method ora --gene-set-from-markers prev_run/tables/markers_all.csv \
  --marker-group "T cell,B cell" --marker-top-n 50

# GSVA-R (group-aware)
python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py \
  --input clustered.h5ad --output results/ \
  --method gsva_r --groupby cell_type --gene-set-db hallmark
```

## See also

- `references/parameters.md` — every CLI flag, library aliases, ORA/GSEA tunables
- `references/methodology.md` — ORA vs GSEA vs GSVA; ranking-metric guide
- `references/output_contract.md` — `enrichment_results.csv` column schema; per-method differences
- Adjacent skills: `sc-markers` / `sc-de` (upstream — produce the rankings consumed here; can also be re-used as gene sets via `--gene-set-from-markers`), `sc-pathway-scoring` (parallel — per-cell scoring against gene sets, NOT per-group enrichment), `sc-gene-programs` (parallel — de-novo factorisation, NOT supervised enrichment), `sc-cell-annotation` (upstream — produces meaningful biological labels for `--groupby`)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`adjustText`, `anndata`, `gseapy`, `matplotlib`, `networkx`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
