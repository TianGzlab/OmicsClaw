---
name: spatial-enrichment
description: Load when running pathway / gene-set enrichment per cluster on a preprocessed spatial AnnData
  via Enrichr (over-representation), GSEA (preranked), or ssGSEA (per-cell scores). Skip when ranking
  spatially variable genes (use spatial-genes); comparing pathways across conditions (use spatial-condition).
trigger: pathway enrichment, gene set enrichment, enrichr, GSEA, ssGSEA, GO, Reactome, MSigDB
tags:
- spatial
- enrichment
- pathway
- gsea
- ssgsea
- enrichr
- gene-set
---

# spatial-enrichment

## When to use

The user has a preprocessed spatial AnnData with cluster labels in
`obs[groupby]` (default `leiden`) and wants pathway / gene-set
enrichment per cluster. Three backends:

- `enrichr` (default) — over-representation against an Enrichr
  hosted gene-set library. Tunables `--enrichr-padj-cutoff`,
  `--enrichr-log2fc-cutoff`, `--enrichr-max-genes`.
- `gsea` — preranked GSEA. Tunables `--gsea-min-size`,
  `--gsea-max-size`, `--gsea-permutation-num`, `--gsea-weight`,
  `--gsea-threads`, `--gsea-seed`.
- `ssgsea` — single-sample GSEA per cell, scores written back to
  `obs[...]`. Tunables `--ssgsea-min-size`, `--ssgsea-max-size`,
  `--ssgsea-weight`.

`--gene-set` selects a hosted library (e.g. `MSigDB_Hallmark_2020`);
`--gene-set-file` accepts a custom GMT. Species: `human` (default)
or `mouse`. For non-spatial enrichment use `sc-enrichment`.

## Inputs & Outputs

**Inputs**

- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)
- Expects `obsm`: `spatial`

**Outputs**

- `tables/enrichment_group_metrics.csv`
- `tables/enrichment_results.csv`
- `tables/enrichment_run_summary.csv`
- `tables/enrichment_significant.csv`
- `tables/enrichment_spatial_points.csv`
- `tables/enrichment_term_group_scores.csv`
- `tables/enrichment_umap_points.csv`
- `tables/ranked_markers.csv`
- `tables/top_enriched_terms.csv`
- `figures/enrichment_barplot.png`
- `figures/enrichment_dotplot.png`
- `figures/enrichment_group_metrics.png`
- `figures/enrichment_group_spatial_context.png`
- `figures/enrichment_group_top_stat_spatial.png`
- `figures/enrichment_group_top_stat_umap.png`
- `figures/enrichment_pvalue_distribution.png`
- `figures/enrichment_score_distribution.png`
- `figures/enrichment_score_violin.png`
- `figures/enrichment_spatial_scores.png`
- `figures/top_enriched_terms.png`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `uns`: `enrichment_results`, `{method}_results`, `enrichr_results`, `gsea_results`, `ssgsea_results`, `enrichment_score_columns`

## Flow

1. Load AnnData; if `obs[groupby]` is missing, auto-cluster with Leiden (or `parser.error` if dataset too small).
2. For Enrichr / GSEA: rank markers per group via `sc.tl.rank_genes_groups` (`--de-method wilcoxon`/`t-test`), then submit to Enrichr or run preranked GSEA.
3. For ssGSEA: compute per-cell pathway scores; write columns to `obs[...]` + register them in `uns["enrichment_score_columns"]` (`_lib/enrichment.py`).
4. Persist canonical results to `uns["enrichment_results"]` plus a per-method copy at `uns[f"{method}_results"]` (`_lib/enrichment.py`).
5. Filter by `--fdr-threshold` + `--n-top-terms`; export per-group ranked tables.
6. Render barplot / dotplot / spatial / violin / score-distribution plots.
7. Save tables + `processed.h5ad` + report.

## Gotchas

- **Default groupby is `leiden`.** `_lib/enrichment.py` and the CLI default `--groupby leiden`. If `obs["leiden"]` is missing, the script auto-runs Leiden — but only if the dataset is large enough; otherwise `spatial_enrichment.py` calls `parser.error("Dataset is too small to auto-compute leiden clusters")`.
- **Enrichr requires internet access.** Enrichr is a hosted API — runs fail in air-gapped environments. Use `--method gsea` or `--method ssgsea` with a local `--gene-set-file` for offline workflows.
- **ssGSEA score-column NAMES are not stable across runs.** `_lib/enrichment.py` constructs them from the geneset library + term name, then registers the list in `uns["enrichment_score_columns"]`. Always read that key — don't hard-code column names.
- **`obs[groupby]` is double-cast.** The wrapper at `spatial_enrichment.py` first casts to `pd.Categorical(...)` (so plotting / report ordering uses sorted categories). Later, `_lib/enrichment.py` (`_ensure_obs_string`) re-casts to plain `str` for the marker-ranking step. The on-disk `processed.h5ad` reflects the final string cast — Categorical ordering on input is lost either way.
- **GSEA permutation tests are slow.** `--gsea-permutation-num` (default 1000) drives runtime; for sketch runs drop to 100. Use `--gsea-threads N` for parallelism.
- **`uns["{method}_results"]` mirrors `uns["enrichment_results"]`.** `_lib/enrichment.py` writes the canonical key plus a per-method alias (`uns["ssgsea_results"]` / `uns["gsea_results"]`). Downstream readers should prefer the canonical key.

## Key CLI

```bash
# Demo
python skills/spatial/spatial-enrichment/spatial_enrichment.py --demo --output /tmp/enr_demo

# Enrichr over-representation (default)
python skills/spatial/spatial-enrichment/spatial_enrichment.py \
  --input preprocessed.h5ad --output results/ \
  --method enrichr --groupby leiden --species human \
  --gene-set MSigDB_Hallmark_2020 --fdr-threshold 0.05 --n-top-terms 20

# GSEA preranked with custom GMT
python skills/spatial/spatial-enrichment/spatial_enrichment.py \
  --input preprocessed.h5ad --output results/ \
  --method gsea --gene-set-file /path/to/library.gmt \
  --gsea-min-size 15 --gsea-max-size 500 --gsea-permutation-num 1000

# ssGSEA per-cell scoring
python skills/spatial/spatial-enrichment/spatial_enrichment.py \
  --input preprocessed.h5ad --output results/ \
  --method ssgsea --gene-set MSigDB_Hallmark_2020 \
  --ssgsea-min-size 10 --ssgsea-max-size 500
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins; gene-set choice
- `references/output_contract.md` — `uns["enrichment_results"]` + ssGSEA `obs[...]` schema
- Adjacent skills: `spatial-preprocess` (upstream), `spatial-domains` (upstream — provides `obs[groupby]`), `spatial-de` (parallel / upstream — provides `rank_genes_groups` ranking), `sc-enrichment` (parallel — non-spatial), `spatial-communication` (parallel — L-R signaling)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `gseapy`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
