---
doc_id: skill-guide-sc-pathway-scoring
title: OmicsClaw Skill Guide — SC Pathway Scoring
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-pathway-scoring]
search_terms: [single-cell pathway scoring, aucell, module score, gene set scoring, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Pathway Scoring

**Status**: implementation-aligned guide derived from the current OmicsClaw `sc-pathway-scoring` skill.

## Purpose

Use this guide when you need to decide:
- whether the current question is really about **per-cell pathway/signature scoring**
- whether AUCell or a lightweight module-score path is a better first pass
- which grouping column and parameters matter most in the current wrapper

## Step 1: Place The Skill In The Workflow

Typical order:
1. `sc-preprocessing`
2. `sc-clustering` or `sc-cell-annotation`
3. `sc-pathway-scoring`
4. interpret pathway activity, then continue to `sc-de` or refined annotation if needed

If the user only says “do enrichment”, first explain that this wrapper scores pathway activity **per cell**, then optionally summarizes it by a label column.

## Step 2: Check The Gene-Set Source

Users must provide one of:
- `--gene-sets <local.gmt>`
- `--gene-set-db hallmark|kegg|go_bp|go_cc|go_mf|reactome`

This is a **required input**, not an optional advanced parameter.

## Step 3: Check The Object

Before running:
- confirm the chosen gene-set source matches the input feature identifiers
- decide whether grouped summaries should use `cell_type`, `leiden`, or another label column
- inspect the matrix state:
  - `score_genes_py` needs normalized expression in `adata.X`
  - `aucell_r` can work on a count-like source, but still benefits from a clean preprocessing workflow

## Step 4: Pick The Method Deliberately

| Method | Best first use | Key parameters | Main caveat |
|--------|----------------|----------------|-------------|
| **aucell_r** | Official AUCell pathway scoring | `gene_sets` / `gene_set_db`, `groupby`, `aucell_auc_max_rank`, `top_pathways` | Requires R packages `AUCell` and `GSEABase` |
| **score_genes_py** | Lightweight module-score style pathway scoring | `gene_sets` / `gene_set_db`, `groupby`, `score_genes_ctrl_size`, `score_genes_n_bins`, `top_pathways` | Requires normalized expression in `adata.X` |

## Step 5: What To Explain Before Running

Use wording like this:

```text
About to run single-cell pathway scoring
  Method: score_genes_py
  Gene-set source: hallmark
  Grouping: cell_type
  Key defaults: score_genes_ctrl_size=50, score_genes_n_bins=25, top_pathways=20
  Note: this scores pathway activity per cell, then summarizes it across the selected labels.
```

## Step 6: Tuning Rules

Tune in this order:
1. `gene_sets / gene_set_db`
2. `groupby`
3. method-specific depth/control parameter
4. `top_pathways`

Guidance:
- fix identifier mismatches before changing numeric parameters
- if `groupby` is omitted, say explicitly that the run can still score cells but grouped summaries will be reduced or absent
- raise `aucell_auc_max_rank` only when signatures are large and the default ranking depth seems too shallow
- increase `score_genes_ctrl_size` only when the user wants a more stable background for the Python module-score path

## Step 7: What To Say After The Run

- If many signatures score near zero: inspect gene-set overlap first.
- If grouped heatmaps are noisy: the issue is often the label column, not the scoring algorithm.
- If the user asks for GO/KEGG enrichment significance: explain that this skill does **activity scoring**, not ORA/GSEA significance testing.

## Official References

- https://www.bioconductor.org/packages/devel/bioc/vignettes/AUCell/inst/doc/AUCell.html
- https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.score_genes.html
