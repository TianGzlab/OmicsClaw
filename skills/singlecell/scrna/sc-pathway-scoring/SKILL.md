---
name: sc-pathway-scoring
description: >-
  Single-cell pathway and gene-set activity scoring for preprocessed scRNA-seq
  data using AUCell or a lightweight normalized-expression module-score path.
version: 0.2.0
author: OmicsClaw Team
license: MIT
tags: [singlecell, pathway-scoring, pathway, geneset, aucell, module-score]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
    - "--method"
    - "--gene-sets"
    - "--gene-set-db"
    - "--species"
    - "--groupby"
    - "--top-pathways"
    - "--aucell-auc-max-rank"
    - "--score-genes-ctrl-size"
    - "--score-genes-n-bins"
    - "--aucell-py-auc-threshold"
    - "--r-enhanced"
    param_hints:
      aucell_r:
        priority: "gene_sets/gene_set_db -> groupby -> aucell_auc_max_rank -> top_pathways"
        params: ["gene_sets", "gene_set_db", "species", "groupby", "aucell_auc_max_rank",
          "top_pathways"]
        defaults: {groupby: "auto-detect cluster/cell_type label when omitted", top_pathways: 20,
          aucell_auc_max_rank: "5% of detected features when omitted", species: "human"}
        requires: ["AUCell", "GSEABase", "local_gmt_or_gene_set_db"]
        tips:
        - "--method aucell_r: Official AUCell Bioconductor scoring path."
        - "--aucell-auc-max-rank: AUCell ranking depth override; leave unset to use
          the wrapper's 5% feature default."
      score_genes_py:
        priority: "gene_sets/gene_set_db -> groupby -> score_genes_ctrl_size -> score_genes_n_bins
          -> top_pathways"
        params: ["gene_sets", "gene_set_db", "species", "groupby", "score_genes_ctrl_size",
          "score_genes_n_bins", "top_pathways"]
        defaults: {groupby: "auto-detect cluster/cell_type label when omitted", top_pathways: 20,
          score_genes_ctrl_size: 50, score_genes_n_bins: 25, species: "human"}
        requires: ["normalized_expression", "local_gmt_or_gene_set_db"]
        tips:
        - "--method score_genes_py: lightweight Python module-score path for normalized
          adata.X."
        - "--score-genes-ctrl-size: number of control genes used for background subtraction."
        - "--score-genes-n-bins: expression binning granularity for control-gene matching."
      aucell_py:
        priority: "gene_sets/gene_set_db -> groupby -> aucell_py_auc_threshold ->
          top_pathways"
        params: ["gene_sets", "gene_set_db", "species", "groupby", "aucell_py_auc_threshold",
          "top_pathways"]
        defaults: {groupby: "auto-detect cluster/cell_type label when omitted", top_pathways: 20,
          aucell_py_auc_threshold: 0.05, species: "human"}
        requires: ["local_gmt_or_gene_set_db"]
        tips:
        - "--method aucell_py: pure Python AUCell implementation -- no R required."
        - "--aucell-py-auc-threshold: fraction of ranked genome for AUC calculation
          (default 0.05)."
        - "AUCell ranks genes per cell by expression, then measures gene-set recovery
          curve AUC."
    saves_h5ad: true
    requires_preprocessed: false
    trigger_keywords:
    - pathway score
    - pathway scoring
    - gene set score
    - module score
    - pathway activity
    - signature score
    script: sc_pathway_scoring.py
---

# Single-Cell Pathway Scoring

## Why This Exists

- Without it: users often jump from clustering to pathway claims without seeing per-cell score evidence.
- With it: this wrapper scores pathway or signature activity per cell, then optionally summarizes it across clusters or cell types.
- Why OmicsClaw: it keeps the AnnData contract stable, exports grouped tables, and renders a reusable pathway-scoring gallery.

## Core Capabilities

1. **Official AUCell execution** via the Bioconductor R package.
2. **Lightweight Python module scoring** on normalized expression.
3. **Per-cell score export** back into `processed.h5ad`.
4. **Grouped pathway summaries** using a user-selected or auto-detected label column.
5. **Stable tables and gallery figures** for downstream interpretation and reuse.

## Scope Boundary

Implemented methods:

1. `aucell_r`
2. `score_genes_py`

This skill focuses on **per-cell pathway or signature scoring**. It does **not** perform ORA or preranked GSEA significance testing. If you want GO/KEGG enrichment significance on a ranked gene list, that should be a separate enrichment skill.

## Input Expectations

- Input object: preferably a preprocessed `.h5ad`
- Gene-set source: one of:
  - `--gene-sets <path/to/file.gmt>`
  - `--gene-set-db hallmark|kegg|go_bp|go_cc|go_mf|reactome`
- Optional grouping column: `--groupby`

Matrix expectations:
- `score_genes_py` expects `X = normalized_expression`
- `aucell_r` prefers normalized expression but can still score a count-like source by ranking genes within each cell

## CLI Reference

```bash
python omicsclaw.py run sc-pathway-scoring \
  --input data.h5ad --gene-set-db hallmark --groupby leiden --output out/

python omicsclaw.py run sc-pathway-scoring \
  --input data.h5ad --method aucell_r --gene-sets pathways.gmt \
  --aucell-auc-max-rank 250 --top-pathways 25 --output out/

python omicsclaw.py run sc-pathway-scoring \
  --input data.h5ad --method score_genes_py --gene-set-db kegg \
  --groupby cell_type --score-genes-ctrl-size 50 --score-genes-n-bins 25 --output out/
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | scoring backend | `aucell_r` or `score_genes_py` |
| `--gene-sets` | local GMT gene-set file | optional if `--gene-set-db` is used |
| `--gene-set-db` | built-in pathway/signature library | `hallmark`, `kegg`, `go_bp`, `go_cc`, `go_mf`, `reactome` |
| `--species` | library organism mapping | used with `--gene-set-db`, default `human` |
| `--groupby` | grouping column for summaries | optional; auto-detected when omitted if a plausible label column exists |
| `--top-pathways` | export/plot size control | wrapper-level output control |
| `--aucell-auc-max-rank` | official AUCell `aucMaxRank` override | only used by `aucell_r` |
| `--score-genes-ctrl-size` | module-score control gene count | only used by `score_genes_py` |
| `--score-genes-n-bins` | module-score expression binning | only used by `score_genes_py` |

## Workflow Position

Typical beginner-friendly flow:

1. `sc-preprocessing`
2. `sc-clustering` or `sc-cell-annotation`
3. `sc-pathway-scoring`
4. follow-up interpretation with `sc-de`, `sc-cell-annotation`, or a future statistical enrichment skill

## What The Figures Mean

- `top_gene_sets.png`: the strongest pathway/signature score shifts after aggregating across all cells
- `group_mean_heatmap.png`: mean pathway scores for each group (cluster/cell type)
- `group_mean_dotplot.png`: same grouped pathway scores, with dot size showing the fraction of cells in that group with above-median scores
- `top_pathway_distributions.png`: score distributions for the top pathways
- `embedding_top_pathways.png`: pathway scores projected back onto the embedding to show where the signature is active

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/enrichment_scores.csv`
- `tables/gene_set_overlap.csv`
- `tables/top_pathways.csv`
- `tables/group_mean_scores.csv` when grouped summaries are available
- `tables/group_high_fraction.csv` when grouped summaries are available
- `figures/top_gene_sets.png`
- `figures/group_mean_heatmap.png` when grouped summaries are available
- `figures/group_mean_dotplot.png` when grouped summaries are available
- `figures/top_pathway_distributions.png`
- `figures/embedding_top_pathways.png` when an embedding exists
- `figure_data/`

Stable AnnData outputs:

- `adata.obs["enrich__*"]` score columns
- `adata.uns["sc_pathway_scoring"]`

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | — | Input `.h5ad` file | required unless `--demo` |
| `--output` | str | — | Output directory | required |
| `--demo` | flag | off | Run with bundled demo data | — |
| `--method` | str | `score_genes_py` | Scoring backend: `aucell_r`, `score_genes_py`, `aucell_py` | validated against METHOD_REGISTRY |
| `--gene-sets` | str | None | Path to local GMT gene-set file | required unless `--gene-set-db` or `--demo` |
| `--gene-set-db` | str | None | Built-in library key: `hallmark`, `kegg`, `go_bp`, `go_cc`, `go_mf`, `reactome` | — |
| `--species` | str | `human` | Organism for gene-set library resolution | — |
| `--groupby` | str | None | Grouping column for summaries; auto-detected when omitted | — |
| `--top-pathways` | int | 20 | Number of top pathways to export/plot | — |
| `--aucell-auc-max-rank` | int | None | AUCell `aucMaxRank` override (default: 5% of detected genes) | aucell_r only |
| `--score-genes-ctrl-size` | int | 50 | Control gene count for background subtraction | score_genes_py only |
| `--score-genes-n-bins` | int | 25 | Expression binning granularity for control-gene matching | score_genes_py only |
| `--aucell-py-auc-threshold` | float | 0.05 | Fraction of ranked genome for AUC calculation | aucell_py only |
| `--seed` | int | 42 | Random seed for AUCell ranking | aucell_py only |
| `--r-enhanced` | flag | off | Also render R Enhanced ggplot2 figures | — |

## R Enhanced Plots

Activated by `--r-enhanced`. Files written to `figures/r_enhanced/`.

| Renderer | Output file | figure_data CSV | Plot description | Required R packages |
|----------|-------------|-----------------|------------------|---------------------|
| `plot_embedding_discrete` | `r_embedding_discrete.png` | `embedding_points.csv` | UMAP/embedding colored by cluster/cell type labels | ggplot2 |
| `plot_embedding_feature` | `r_embedding_feature.png` | `embedding_points.csv` | UMAP/embedding colored by top pathway score | ggplot2 |

## Current Limitations

- This skill scores pathway activity; it does not report GO/KEGG enrichment significance.
- `score_genes_py` is a practical lightweight scoring path, not a full GSVA/ssGSEA implementation.
- `aucell_r` depends on local R packages (`AUCell`, `GSEABase`).
