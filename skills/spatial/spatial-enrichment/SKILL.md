---
name: spatial-enrichment
description: >-
  Pathway and gene-set enrichment analysis for spatial transcriptomics using
  ORA-style enrichr, preranked GSEA, or ssGSEA with local-first gene-set
  resolution and method-aware parameter controls.
version: 0.5.0
author: OmicsClaw Team
license: MIT
tags: [spatial, enrichment, enrichr, gsea, ssgsea, pathway, gene-set, GO, Reactome, MSigDB]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--de-corr-method"
      - "--de-method"
      - "--enrichr-log2fc-cutoff"
      - "--enrichr-max-genes"
      - "--enrichr-padj-cutoff"
      - "--fdr-threshold"
      - "--gene-set"
      - "--gene-set-file"
      - "--groupby"
      - "--gsea-ascending"
      - "--gsea-max-size"
      - "--gsea-min-size"
      - "--gsea-permutation-num"
      - "--gsea-ranking-metric"
      - "--gsea-seed"
      - "--gsea-threads"
      - "--gsea-weight"
      - "--method"
      - "--n-top-terms"
      - "--no-gsea-ascending"
      - "--no-ssgsea-ascending"
      - "--source"
      - "--species"
      - "--ssgsea-ascending"
      - "--ssgsea-correl-norm-type"
      - "--ssgsea-max-size"
      - "--ssgsea-min-size"
      - "--ssgsea-sample-norm-method"
      - "--ssgsea-seed"
      - "--ssgsea-threads"
      - "--ssgsea-weight"
    param_hints:
      enrichr:
        priority: "source/gene_set_file → de_method/de_corr_method → enrichr_padj_cutoff/log2fc_cutoff → enrichr_max_genes"
        params: ["groupby", "source", "species", "gene_set", "gene_set_file", "de_method", "de_corr_method", "enrichr_padj_cutoff", "enrichr_log2fc_cutoff", "enrichr_max_genes", "fdr_threshold", "n_top_terms"]
        defaults: {groupby: "leiden", source: "omicsclaw_core", species: "human", de_method: "wilcoxon", de_corr_method: "benjamini-hochberg", enrichr_padj_cutoff: 0.05, enrichr_log2fc_cutoff: 1.0, enrichr_max_genes: 200, fdr_threshold: 0.05, n_top_terms: 20}
        requires: ["obs.groupby", "X_log_normalized"]
        tips:
          - "`enrichr` in OmicsClaw is an ORA-style marker enrichment path: it first ranks markers with Scanpy, then enriches positive markers per group."
          - "--source: choose `omicsclaw_core` for a stable local-first library, or an external library key such as `GO_Biological_Process` / `MSigDB_Hallmark` when GSEApy can resolve it."
          - "--gene-set-file: OmicsClaw wrapper-level override for local `.json` or `.gmt` gene-set libraries."
          - "--de-method / --de-corr-method: upstream Scanpy ranking controls that directly affect which markers enter ORA."
          - "--enrichr-padj-cutoff / --enrichr-log2fc-cutoff / --enrichr-max-genes: wrapper-level positive-marker selection rules before enrichment."
      gsea:
        priority: "source/gene_set_file → de_method/de_corr_method → gsea_ranking_metric → gsea_min_size/max_size → gsea_permutation_num/weight"
        params: ["groupby", "source", "species", "gene_set", "gene_set_file", "de_method", "de_corr_method", "gsea_ranking_metric", "gsea_min_size", "gsea_max_size", "gsea_permutation_num", "gsea_weight", "gsea_ascending", "gsea_threads", "gsea_seed", "fdr_threshold", "n_top_terms"]
        defaults: {groupby: "leiden", source: "omicsclaw_core", species: "human", de_method: "wilcoxon", de_corr_method: "benjamini-hochberg", gsea_ranking_metric: "auto", gsea_min_size: 15, gsea_max_size: 500, gsea_permutation_num: 100, gsea_weight: 1.0, gsea_ascending: false, gsea_threads: 1, gsea_seed: 123, fdr_threshold: 0.05, n_top_terms: 20}
        requires: ["obs.groupby", "X_log_normalized"]
        tips:
          - "--gsea-ranking-metric: OmicsClaw wrapper-level choice of how Scanpy marker rankings are converted into a preranked list; `auto` prefers `scores`, then `logfoldchanges`."
          - "--gsea-min-size / --gsea-max-size / --gsea-permutation-num / --gsea-weight / --gsea-ascending / --gsea-threads / --gsea-seed: official GSEApy `prerank()` controls."
          - "`gsea` keeps the full ranked gene list per group, so it is more appropriate than ORA when the user wants subtle coordinated pathway shifts instead of thresholded marker overlap."
      ssgsea:
        priority: "source/gene_set_file → ssgsea_sample_norm_method/correl_norm_type → ssgsea_min_size/max_size → ssgsea_weight"
        params: ["groupby", "source", "species", "gene_set", "gene_set_file", "ssgsea_sample_norm_method", "ssgsea_correl_norm_type", "ssgsea_min_size", "ssgsea_max_size", "ssgsea_weight", "ssgsea_ascending", "ssgsea_threads", "ssgsea_seed", "n_top_terms"]
        defaults: {groupby: "leiden", source: "omicsclaw_core", species: "human", ssgsea_sample_norm_method: "rank", ssgsea_correl_norm_type: "rank", ssgsea_min_size: 15, ssgsea_max_size: 500, ssgsea_weight: 0.25, ssgsea_ascending: false, ssgsea_threads: 1, ssgsea_seed: 123, n_top_terms: 20}
        requires: ["obs.groupby", "X_log_normalized"]
        tips:
          - "`ssgsea` in the current OmicsClaw wrapper runs on group-level mean expression profiles, not on every spot independently."
          - "--ssgsea-sample-norm-method / --ssgsea-correl-norm-type / --ssgsea-min-size / --ssgsea-max-size / --ssgsea-weight / --ssgsea-ascending / --ssgsea-threads / --ssgsea-seed: official GSEApy `ssgsea()` controls."
          - "OmicsClaw projects selected group-level ssGSEA scores back to `adata.obs` for visualization; this is a display layer rather than extra statistical testing."
    legacy_aliases: [enrichment]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🛤️"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
      - kind: pip
        package: gseapy
        bins: []
    trigger_keywords:
      - pathway enrichment
      - gene set enrichment
      - enrichr
      - GSEA
      - ssGSEA
      - GO
      - Reactome
      - MSigDB
---

# 🛤️ Spatial Enrichment

You are **Spatial Enrichment**, the pathway and gene-set enrichment skill for
OmicsClaw. Your role is to translate spatial group markers or ranked gene
signatures into biological programs while keeping ORA, preranked GSEA, and
ssGSEA conceptually separate.

## Why This Exists

- **Without it**: users often move between marker discovery and pathway
  interpretation with ad-hoc exports, ambiguous gene-set sources, and no clear
  distinction between ORA and rank-based enrichment.
- **With it**: OmicsClaw builds the marker or ranking input internally, applies
  method-specific enrichment, and exports standardized tables, figures, and
  reproducibility helpers.
- **Why OmicsClaw**: the wrapper keeps enrichment local-first, exposes
  method-aware parameter hints, and makes later gene-set source extensions easy
  without breaking the user-facing output contract.

## Core Capabilities

1. **Enrichr-style ORA**: per-group enrichment on positive marker genes.
2. **Preranked GSEA**: full ranked marker lists per group with NES-based
   interpretation.
3. **ssGSEA**: single-sample-style enrichment on group-level mean expression
   profiles.
4. **Local-first gene-set resolution**: supports built-in OmicsClaw signatures,
   local `.json` / `.gmt` files, and remote library resolution through GSEApy.
5. **Deterministic fallback behavior**: if a remote gene-set library cannot be
   resolved, OmicsClaw records a warning and falls back to a local library.
6. **Marker export**: writes the ranked marker table used as enrichment input
   for auditability and extension.
7. **Score projection for visualization**: selected ssGSEA group scores are
   mapped back to observations for spatial plotting.
8. **Standard Python gallery**: emits a recipe-driven enrichment gallery with
   overview, diagnostic, supporting, and uncertainty panels backed by the
   shared `skills/spatial/_lib/viz` layer.
9. **Figure-ready exports**: writes `figure_data/` CSVs plus a gallery manifest
   so downstream tools can restyle the same enrichment result without
   recomputing it.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `adata.X`, `obs[groupby]`; `obsm["spatial"]` optional for spatial score maps | `processed.h5ad` |
| Demo | n/a | `--demo` flag | Runs spatial-preprocess demo first |

## Input Matrix Convention

The current wrapper uses log-normalized expression in `adata.X` for all three
methods, but the statistical role differs:

| Method | Input representation | Why |
|--------|----------------------|-----|
| `enrichr` | Scanpy marker table built from `adata.X` | ORA depends on thresholded positive markers, not on raw counts |
| `gsea` | full ranked marker list built from `adata.X` | preranked GSEA works on ordered group-specific marker statistics |
| `ssgsea` | group-level mean expression profiles from `adata.X` | current wrapper summarizes expression per group before gene-set scoring |

**Core principle**:

- Use `enrichr` when the user wants pathway interpretation of thresholded marker
  genes.
- Use `gsea` when the user wants pathway shifts across the full ranked list.
- Use `ssgsea` when the user wants group-level enrichment scores rather than
  p-value-based per-pathway testing.

## Workflow

1. **Load**: read the preprocessed h5ad.
2. **Validate**: confirm `groupby` exists; if default `leiden` is missing,
   OmicsClaw can compute a minimal clustering pass.
3. **Resolve gene sets**: choose local built-in signatures, a local
   `.json` / `.gmt` library, or an external GSEApy library key.
4. **Build enrichment input**:
   - `enrichr`: positive markers per group
   - `gsea`: full ranked marker list per group
   - `ssgsea`: group-level mean expression matrix
5. **Run enrichment** and normalize results into a shared output table.
6. **Render the standard gallery**: build the OmicsClaw narrative gallery with
   grouping context, canonical enrichment overviews, projected diagnostics, and
   uncertainty panels.
7. **Export figure-ready data**: write `figure_data/*.csv` and
   `figure_data/manifest.json` for downstream customization.
8. **Export**: write enrichment tables, `report.md`, `result.json`, figures,
   and reproducibility helpers.

## Visualization Contract

OmicsClaw treats `spatial-enrichment` visualization as a two-layer system:

1. **Python standard gallery**: the canonical result layer. This is the
   default output users should inspect first.
2. **R customization layer**: an optional styling and publication layer that
   reads `figure_data/` and does not recompute ORA, GSEA, or ssGSEA.

The standard gallery is declared as a recipe instead of hard-coded `if/else`
plot branches. Current gallery roles include:

- `overview`: grouping labels on tissue plus canonical enrichment barplot and
  dotplot views
- `diagnostic`: projected top-stat burden maps and, when available, spatial
  ssGSEA score maps
- `supporting`: top-term summaries, per-group burden barplots, and ssGSEA
  violin plots when score columns exist
- `uncertainty`: adjusted p-value distributions and enrichment score
  distributions

## CLI Reference

```bash
# Default local-first ORA
oc run spatial-enrichment \
  --input <processed.h5ad> --output <dir>

# Enrichr-style ORA using an external library key when available
oc run spatial-enrichment \
  --input <processed.h5ad> --method enrichr \
  --source GO_Biological_Process --species human \
  --de-method wilcoxon --de-corr-method benjamini-hochberg \
  --enrichr-padj-cutoff 0.05 --enrichr-log2fc-cutoff 1.0 \
  --enrichr-max-genes 200 --output <dir>

# Preranked GSEA
oc run spatial-enrichment \
  --input <processed.h5ad> --method gsea \
  --source MSigDB_Hallmark \
  --gsea-ranking-metric auto --gsea-min-size 15 --gsea-max-size 500 \
  --gsea-permutation-num 100 --gsea-weight 1.0 --gsea-threads 1 \
  --output <dir>

# ssGSEA with local gene-set file
oc run spatial-enrichment \
  --input <processed.h5ad> --method ssgsea \
  --gene-set-file ./custom_sets.gmt \
  --ssgsea-sample-norm-method rank \
  --ssgsea-correl-norm-type rank \
  --output <dir>

# Demo mode
oc run spatial-enrichment --demo --output /tmp/enrich_demo

# Direct script entrypoint
python skills/spatial/spatial-enrichment/spatial_enrichment.py \
  --input <processed.h5ad> --method enrichr --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Run pathway enrichment on my spatial cluster markers"
- "Use preranked GSEA instead of thresholded ORA"
- "Score hallmark-like programs across spatial groups with ssGSEA"

## Algorithm / Methodology

### Enrichr

1. **Marker ranking**: `scanpy.tl.rank_genes_groups(...)` builds per-group marker
   statistics.
2. **Positive marker selection**: OmicsClaw keeps genes that pass the wrapper
   marker cutoffs (`enrichr_padj_cutoff`, `enrichr_log2fc_cutoff`,
   `enrichr_max_genes`).
3. **ORA engine**:
   - preferred: `gseapy.enrich(...)` on a local gene-set dictionary
   - fallback: local hypergeometric testing with BH correction

### GSEA

1. **Marker ranking**: same Scanpy marker table as above.
2. **Ranking metric**: OmicsClaw chooses or auto-resolves the ranking column.
3. **Prerank engine**:
   - preferred: `gseapy.prerank(...)`
   - fallback: local rank-based permutation approximation

### ssGSEA

1. **Expression matrix**: OmicsClaw computes group-level mean expression
   profiles from `adata.X`.
2. **Scoring engine**:
   - preferred: `gseapy.ssgsea(...)`
   - fallback: simplified local score approximation
3. **Visualization projection**: selected group-level scores are mapped back to
   observations for plotting.

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── enrichment_group_spatial_context.png
│   ├── enrichment_barplot.png
│   ├── enrichment_dotplot.png
│   ├── enrichment_group_top_stat_spatial.png
│   ├── enrichment_spatial_scores.png        (ssGSEA when projected score columns exist)
│   ├── enrichment_group_top_stat_umap.png   (when UMAP is available)
│   ├── top_enriched_terms.png
│   ├── enrichment_group_metrics.png
│   ├── enrichment_score_violin.png          (ssGSEA)
│   ├── enrichment_pvalue_distribution.png   (enrichr / gsea)
│   ├── enrichment_score_distribution.png
│   └── manifest.json
├── figure_data/
│   ├── enrichment_results.csv
│   ├── enrichment_significant.csv
│   ├── ranked_markers.csv
│   ├── top_enriched_terms.csv
│   ├── enrichment_group_metrics.csv
│   ├── enrichment_term_group_scores.csv
│   ├── enrichment_run_summary.csv
│   ├── enrichment_spatial_points.csv
│   ├── enrichment_umap_points.csv
│   └── manifest.json
├── tables/
│   ├── enrichment_results.csv
│   ├── enrichment_significant.csv
│   ├── ranked_markers.csv
│   ├── top_enriched_terms.csv
│   └── enrichment_group_metrics.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── r_visualization.sh
    └── requirements.txt
```

## Safety

- **Local-first**: OmicsClaw prefers local gene-set dictionaries and records any
  remote-library fallback explicitly.
- **Method separation**: ORA, GSEA, and ssGSEA answer different questions and
  should not be presented as interchangeable evidence.
- **Two-layer visualization design**: Python plots are the canonical standard
  gallery; the optional R layer consumes `figure_data/` for publication-style
  refinement without recomputing the science.
- **No keyword filtering**: pathway relevance should be interpreted after
  significance and score ranking, not by pre-filtering term names.
- **Audit trail**: ranked markers, resolved library mode, and warnings are
  exported for inspection.

## Integration With Orchestrator

**Trigger conditions**:

- pathway enrichment
- gene set enrichment
- enrichr
- GSEA
- ssGSEA
- GO / Reactome / MSigDB interpretation

**Chaining**:

- often follows `spatial-de`
- can also run directly on clustered output from `spatial-preprocess`

## Citations

- [GSEApy](https://gseapy.readthedocs.io/) — Python enrichment toolkit
- [Enrichr](https://maayanlab.cloud/Enrichr/) — pathway and signature library service
- [MSigDB](https://www.gsea-msigdb.org/) — Molecular Signatures Database
