---
name: sc-enrichment
description: >-
  Statistical enrichment analysis for single-cell RNA-seq using ORA or
  preranked GSEA on marker or differential-expression rankings. This skill is
  for GO/KEGG/Reactome/Hallmark term significance, not per-cell pathway
  activity scoring.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, enrichment, ORA, GSEA, GO, KEGG, Reactome, Hallmark]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--gene-set-db"
      - "--gene-set-from-markers"
      - "--gene-sets"
      - "--engine"
      - "--groupby"
      - "--gsea-max-size"
      - "--gsea-min-size"
      - "--gsea-permutation-num"
      - "--gsea-ranking-metric"
      - "--gsea-seed"
      - "--gsea-weight"
      - "--marker-group"
      - "--marker-top-n"
      - "--method"
      - "--ora-log2fc-cutoff"
      - "--ora-max-genes"
      - "--ora-padj-cutoff"
      - "--ranking-method"
      - "--species"
      - "--top-terms"
    param_hints:
      ora:
        priority: "gene_sets/gene_set_db/gene_set_from_markers -> engine -> upstream ranking source -> groupby/ranking_method -> ora thresholds"
        params: ["gene_sets", "gene_set_db", "gene_set_from_markers", "marker_group", "marker_top_n", "engine", "groupby", "ranking_method", "ora_padj_cutoff", "ora_log2fc_cutoff", "ora_max_genes", "species", "top_terms"]
        defaults: {engine: "auto", ranking_method: "wilcoxon", ora_padj_cutoff: 0.05, ora_log2fc_cutoff: 0.25, ora_max_genes: 200, species: "human", top_terms: 18}
        requires: ["gene_set_source", "normalized_expression_or_upstream_ranking"]
        tips:
          - "--method ora: best for thresholded marker/DE gene lists when you want the most enriched terms quickly."
          - "If you only provide a processed h5ad, the wrapper can auto-rank cluster markers first using `ranking_method`."
          - "If you already ran `sc-markers` or `sc-de`, passing that output directory lets the wrapper reuse exported rankings."
      gsea:
        priority: "gene_sets/gene_set_db/gene_set_from_markers -> engine -> upstream ranking source -> groupby/ranking_method -> gsea ranking controls"
        params: ["gene_sets", "gene_set_db", "gene_set_from_markers", "marker_group", "marker_top_n", "engine", "groupby", "ranking_method", "gsea_ranking_metric", "gsea_min_size", "gsea_max_size", "gsea_permutation_num", "gsea_weight", "gsea_seed", "species", "top_terms"]
        defaults: {engine: "auto", ranking_method: "wilcoxon", gsea_ranking_metric: "auto", gsea_min_size: 5, gsea_max_size: 500, gsea_permutation_num: 100, gsea_weight: 1.0, gsea_seed: 123, species: "human", top_terms: 18}
        requires: ["gene_set_source", "full_ranked_gene_list"]
        tips:
          - "--method gsea: keeps the full ranking and is better when subtle coordinated shifts matter more than hard DEG thresholds."
          - "If the input is a filtered marker table, OmicsClaw may rebuild a fuller ranking from `processed.h5ad`."
          - "`gsea_ranking_metric=auto` prefers `stat`, then `scores`, then `logfoldchanges`."
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "🧭"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: gseapy
        bins: []
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - sc enrichment
      - single-cell enrichment
      - GO enrichment
      - KEGG enrichment
      - GSEA
      - ORA
      - pathway enrichment
---

# Single-Cell Statistical Enrichment

## Why This Exists

- **Without it**: users jump from marker genes to pathway interpretation with ad-hoc exports and no clear distinction between statistical enrichment and per-cell pathway scoring.
- **With it**: OmicsClaw can reuse `sc-markers` / `sc-de` outputs or auto-rank a clustered h5ad, then run ORA or preranked GSEA with standardized outputs.
- **Why OmicsClaw**: it keeps the workflow local-first, makes upstream/downstream guidance explicit, and preserves the singlecell output contract.

## Core Capabilities

1. **ORA** on positive marker / DEG lists.
2. **Preranked GSEA** on full group-specific rankings.
3. **Flexible upstream intake**:
   - output directory from `sc-markers`
   - output directory from `sc-de`
   - processed `.h5ad` with automatic cluster-vs-rest ranking
4. **Marker-derived custom gene sets**:
   - convert one or more `sc-markers` groups into gene sets directly
4. **Local-first gene-set sources**:
   - local `.gmt` / `.json`
   - built-in library keys via `--gene-set-db`
5. **Standard outputs**:
   - `processed.h5ad`
   - figures, tables, figure-ready CSV exports
   - report and reproducibility helpers

## Scope Boundary

This skill performs **statistical enrichment**.

- Use `sc-enrichment` when you want GO / KEGG / Reactome / Hallmark terms that are statistically over-represented or enriched.
- Use `sc-pathway-scoring` when you want a pathway/signature score for each individual cell.

In plain language:

- `sc-enrichment` answers: “which biological terms are significantly enriched?”
- `sc-pathway-scoring` answers: “how active is this gene signature in each cell?”

## Input Formats

| Format | Supported? | Notes |
|--------|------------|-------|
| `sc-markers` output directory | yes | reuses `tables/markers_all.csv` when possible |
| `sc-de` output directory | yes | reuses `tables/de_full.csv` when possible |
| processed `.h5ad` | yes | auto-ranks cluster-vs-rest markers when needed |
| `--demo` | yes | PBMC-style demo with built-in demo gene sets |

## Input Expectations

- A gene-set source is required unless `--demo` is used:
  - `--gene-sets <local.gmt/json>`
  - or `--gene-set-db <hallmark|kegg|go_bp|go_cc|go_mf|reactome>`
  - or `--gene-set-from-markers <sc-markers-output-dir-or-table>`
- If you pass a plain `.h5ad`, the wrapper expects normalized expression in `adata.X` and a usable cluster/cell-type column.
- If you want condition DE enrichment with biological replicates, run `sc-de` first and then pass that output directory here.
- If you use `--gene-set-from-markers`, you can additionally specify:
  - `--marker-group <cluster or comma-separated groups>`
  - `--marker-top-n <N|all>`

## Environment And Installation

### Python side

Both `sc-enrichment` and `sc-pathway-scoring` share the same Python extra:

```bash
pip install -e ".[singlecell-enrichment]"
```

This installs `gseapy`, which is needed for:

- built-in library keys such as `--gene-set-db hallmark`
- Python GSEA execution
- local-first enrichment fallback helpers

### R side

If you want `--engine r`, the most reliable path is to install **prebuilt**
Bioconductor packages into the same conda environment instead of compiling
everything from source inside R.

Recommended approach:

```bash
micromamba install -p <your_conda_prefix> -y \
  --override-channels \
  -c https://conda.anaconda.org/conda-forge \
  -c https://conda.anaconda.org/bioconda \
  bioconductor-clusterprofiler bioconductor-enrichplot bioconductor-ggtree
```

Human explanation:

- `engine=python` needs the Python extra only
- `engine=r` additionally needs the R `clusterProfiler/enrichplot` stack
- `engine=auto` prefers the R path when that stack is installed, and otherwise
  falls back to the Python implementation

Important note:

- OmicsClaw uses the current conda environment's `Rscript` and prioritizes that
  environment's private R library path
- if old package versions are left in the private R library, they can override
  newer packages that already exist inside the conda environment

## Workflow

1. Load the upstream output or processed h5ad.
2. Preflight the question:
   - statistical enrichment here
   - per-cell activity scoring belongs in `sc-pathway-scoring`
3. Resolve the ranking source:
   - reuse marker / DE tables
   - or auto-rank cluster markers from h5ad
4. Resolve gene sets from a local file or built-in database key.
5. Run ORA or preranked GSEA.
6. Export tables, figures, `figure_data`, report, and `processed.h5ad`.

## CLI Reference

```bash
python omicsclaw.py run sc-enrichment \
  --input <sc-markers-output-dir> \
  --method ora \
  --engine auto \
  --gene-set-db go_bp \
  --output <dir>

python omicsclaw.py run sc-enrichment \
  --input <processed.h5ad> \
  --groupby leiden \
  --method gsea \
  --engine r \
  --gene-sets <local.gmt> \
  --output <dir>

python omicsclaw.py run sc-enrichment \
  --input <sc-de-output-dir> \
  --method ora \
  --gene-set-from-markers <sc-markers-output-dir> \
  --marker-group "CD4 T cells,CD8 T cells" \
  --marker-top-n 100 \
  --output <dir>

python omicsclaw.py run sc-enrichment --demo --method ora --output <dir>
```

## Public Parameters

| Parameter | Role |
|-----------|------|
| `--method` | `ora` or `gsea` |
| `--engine` | `auto`, `python`, or `r` |
| `--gene-sets` | local GMT/JSON gene-set file |
| `--gene-set-db` | built-in library key (`hallmark`, `kegg`, `go_bp`, `reactome`, …) |
| `--gene-set-from-markers` | derive gene sets directly from a `sc-markers` output directory or marker table |
| `--marker-group` | which marker groups to convert into gene sets (comma-separated); omit to convert all groups |
| `--marker-top-n` | how many marker genes to keep per selected group, or `all` |
| `--groupby` | grouping column when auto-ranking from h5ad |
| `--ranking-method` | marker-ranking method used for auto-generated rankings |
| `--top-terms` | how many terms to emphasize in figures/reports |
| `--ora-padj-cutoff` | ORA significance filter on the input ranking |
| `--ora-log2fc-cutoff` | ORA effect-size filter when fold change exists |
| `--ora-max-genes` | maximum input genes per group for ORA |
| `--gsea-ranking-metric` | which column drives preranked GSEA |
| `--gsea-min-size` / `--gsea-max-size` | gene-set size limits for GSEA |
| `--gsea-permutation-num` | permutation count for GSEA |
| `--gsea-weight` | weighting exponent for GSEA |
| `--gsea-seed` | deterministic GSEA seed |

### Which parameters are truly required?

For real runs, the minimum required information is:

1. input source
2. output directory
3. one gene-set source

That means:

- `--input ...` or `--demo`
- `--output ...`
- and one of:
  - `--gene-sets ...`
  - `--gene-set-db ...`
  - `--gene-set-from-markers ...`

Everything else has a default and can be tuned later.

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/enrichment_results.csv`
- `tables/enrichment_significant.csv`
- `tables/group_summary.csv`
- `tables/ranking_input.csv`
- `figure_data/manifest.json`
- `reproducibility/commands.sh`

### Visualization Contract

The standard gallery focuses on:

- top enriched terms across groups
- group-by-term comparison
- group summary
- GSEA running-score details when applicable
- when `engine=r` and the R stack is available, supplementary clusterProfiler figures such as enrichmap and ridgeplot

## Beginner Guidance

- After clustering and marker discovery, use `sc-enrichment` to ask “what biology do these groups represent?”
- If you instead want “where is this pathway active in the embedding?”, use `sc-pathway-scoring`.
- If you need stronger condition-aware rankings first, run `sc-de` before enrichment.

## Related Skills

- `sc-markers`
- `sc-de`
- `sc-pathway-scoring`
- `sc-cell-annotation`
