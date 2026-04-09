---
doc_id: skill-guide-sc-enrichment
domain: singlecell
title: Single-cell statistical enrichment guide
skill: sc-enrichment
related_skills: [sc-enrichment]
version: 0.1.0
status: implementation-aligned
---

# sc-enrichment

## What It Is

`sc-enrichment` performs **statistical enrichment** on marker or DE rankings.

Use it for questions like:
- “What GO / KEGG terms explain this cluster?”
- “Which Hallmark pathways are enriched in this differential expression contrast?”

Do **not** use it when you want a per-cell signature score on the embedding.  
That job belongs to `sc-pathway-scoring`.

Quick beginner translation:

- `sc-enrichment`: “which GO/KEGG/Hallmark terms are statistically enriched?”
- `sc-pathway-scoring`: “how active is this gene set in each cell?”

## Typical Workflow Position

Common paths:

1. `sc-clustering` -> `sc-markers` -> `sc-enrichment`
2. `sc-clustering` -> `sc-de` -> `sc-enrichment`
3. `sc-cell-annotation` -> `sc-de` -> `sc-enrichment`

If the user only gives a processed h5ad, the wrapper can auto-rank cluster-vs-rest markers first.

## Methods

| Method | Best for | Key inputs |
|--------|----------|------------|
| `ora` | thresholded marker / DEG lists | gene-set source, optional h5ad `groupby`, ORA cutoffs |
| `gsea` | full ranked lists and subtle coordinated shifts | gene-set source, ranking metric, GSEA size/permutation controls |

Implementation engines:

- `engine=auto`
  - prefer R `clusterProfiler/enrichplot` when available
  - otherwise fall back to the Python implementation
- `engine=python`
  - local Python execution only
- `engine=r`
  - require R packages `clusterProfiler` and `enrichplot`

## Installation Advice

### Python dependency

`sc-enrichment` and `sc-pathway-scoring` share the same Python extra:

```bash
pip install -e ".[singlecell-enrichment]"
```

This is the correct first install step for both skills.

### R dependency

If the user wants `engine=r`, the stable recommendation is:

- install prebuilt Bioconductor packages into the **same conda environment**
- do **not** default to source compilation inside R unless you really have to

Why:

- source installs are slower
- version mismatches are more common
- old packages left in the private R library can override newer conda packages

## Required Inputs

Real runs need one gene-set source:

- `--gene-sets <local.gmt/json>`
- or `--gene-set-db <hallmark|kegg|go_bp|go_cc|go_mf|reactome>`
- or `--gene-set-from-markers <sc-markers-output-dir-or-table>`

If the input is a plain h5ad and not an upstream output directory, the wrapper also needs a usable cluster / cell-type column for automatic ranking.

So the truly required inputs are:

1. `input`
2. `output`
3. one gene-set source

Everything else can start from defaults.

## Beginner Translation Of Key Parameters

- `groupby`
  - when auto-ranking from h5ad, this decides which labels are compared
- `ranking_method`
  - how the wrapper generates marker rankings from h5ad before enrichment
- `engine`
  - choose Python, R, or auto-prefer-R execution
- `ora_padj_cutoff`
  - which genes count as significant enough to enter ORA
- `ora_log2fc_cutoff`
  - how strong a fold change a gene should have before ORA uses it
- `gsea_ranking_metric`
  - which ranking column drives preranked GSEA
- `top_terms`
  - how many top terms are emphasized in figures and the report

## Gene-set Sources

Built-in library keys currently include:

- `hallmark`
- `kegg`
- `go_bp`
- `go_cc`
- `go_mf`
- `reactome`

Users can also provide a custom GMT/JSON file, which is the right choice for lab-specific marker signatures.

Practical advice:

- use `gene_set_db` when you want quick GO/KEGG/Hallmark interpretation
- use `gene_sets` when you already have a lab-defined marker/signature file
- use `gene_set_from_markers` when you want to turn one or more cluster marker lists into enrichment gene sets directly
- first-time `gene_set_db` resolution may need network access to populate cache

## Marker-derived Gene Sets

This is useful when the user says something like:

- “用 cluster 2 的 top100 marker 做富集”
- “把 T cell 和 NK 的 marker 当成 gene set”

Current parameters:

- `--gene-set-from-markers <sc-markers-output-dir-or-table>`
- `--marker-group <group or comma-separated groups>`
- `--marker-top-n <N|all>`

Behavior:

- if `marker_group` is omitted, each marker group becomes its own gene set
- if `marker_group` is provided, only those groups are converted
- if `marker_top_n=all`, the full exported marker list for each selected group is used

## Output Meaning

- `tables/enrichment_results.csv`
  - all tested terms
- `tables/enrichment_significant.csv`
  - statistically significant subset
- `tables/ranking_input.csv`
  - the ranking that actually drove ORA/GSEA
- `figures/top_terms_bar.png`
  - top enriched terms across groups
- `figures/group_term_dotplot.png`
  - which terms are strongest in which groups
- `figures/group_enrichment_summary.png`
  - how many significant terms each group has
- `figures/gsea_running_scores.png`
  - top running enrichment-score panels for GSEA
- `figures/enrichmap.png`
  - term-overlap network summarizing how enriched terms relate to each other
- `figures/ridgeplot.png`
  - ranking-metric distributions for top enriched terms
