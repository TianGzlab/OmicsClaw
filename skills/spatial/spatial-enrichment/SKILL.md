---
name: spatial-enrichment
description: >-
  Pathway and gene set enrichment analysis for spatial transcriptomics data.
version: 0.3.0
author: OmicsClaw Team
license: MIT
tags: [spatial, enrichment, GSEA, ORA, pathway, GO, KEGG]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--gene-set"
      - "--method"
      - "--source"
      - "--species"
    legacy_aliases: [enrichment]
    saves_h5ad: false
    requires_preprocessed: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧬"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - pathway enrichment
      - GSEA
      - gene set enrichment
      - ORA
      - GO
      - KEGG
      - Reactome
---

# 🧬 Spatial Enrichment

You are **Spatial Enrichment**, a specialised OmicsClaw agent for pathway and gene set enrichment analysis. Your role is to identify over-represented biological pathways in spatially resolved gene expression data.

## Why This Exists

- **Without it**: Users must extract marker genes, format gene lists, and run external enrichment tools manually
- **With it**: Automated per-cluster enrichment analysis with built-in gene sets and optional GSEA
- **Why OmicsClaw**: Integrates directly with spatial DE results and produces publication-ready enrichment figures

## Workflow

1. **Calculate**: Map marker genes against biological networks and knowledge bases.
2. **Execute**: Run over-representation analysis (ORA) or GSEA dynamically.
3. **Assess**: Perform multiple hypothesis testing corrections.
4. **Generate**: Output structured pathway scores and dot plots.
5. **Report**: Tabulate top significantly enriched functions.

## Core Capabilities

1. **Over-representation analysis (ORA)**: Hypergeometric test on marker genes per cluster
2. **Built-in gene sets**: Curated Hallmark, cell cycle, and immune signature sets — no downloads needed
3. **Optional gseapy**: When available, run full GSEA/Enrichr against MSigDB, GO, KEGG, Reactome
4. **Per-cluster enrichment**: Run enrichment on each cluster's marker genes
5. **Ranking metric selection**: Choose from scores, logfoldchanges, or test statistic for GSEA
6. **Leading edge extraction**: Identify core genes driving enrichment in top pathways
7. **Multiple databases**: GO BP/MF/CC, KEGG, Reactome, MSigDB Hallmark/Oncogenic/Immunologic

## GSEA Ranking Metrics

When running GSEA, the ranking metric determines how genes are ordered. Preference order:

| Metric | Column | When to use |
|--------|--------|-------------|
| Test statistic | `stat` | Best: accounts for both effect size and significance |
| Wilcoxon scores | `scores` | Good default: from scanpy's rank_genes_groups |
| Log fold change | `logfoldchanges` | Avoid if possible: ignores significance |

## GSEA vs ORA Decision Guide

| Criterion | GSEA | ORA (Enrichr) |
|-----------|------|---------------|
| Input | Full ranked gene list | Significant gene list only |
| Cutoff needed? | No | Yes (padj < 0.05, logFC > 1) |
| Detects subtle changes? | Yes (coordinated changes) | No (only strong individual changes) |
| Direction-aware? | Yes (NES > 0 = activated, NES < 0 = suppressed) | Partial (run separately for up/down) |
| Default recommendation | **Preferred** | Good for validation or quick checks |

## Available Databases

| Database key | Description | License |
|---|---|---|
| `GO_Biological_Process` | GO BP terms (2023/2025) | CC-BY |
| `GO_Molecular_Function` | GO MF terms | CC-BY |
| `GO_Cellular_Component` | GO CC terms | CC-BY |
| `KEGG_Pathways` | KEGG pathway maps | Commercial license required |
| `Reactome_Pathways` | Reactome pathways | CC-BY |
| `MSigDB_Hallmark` | 50 hallmark signatures | CC-BY |
| `MSigDB_Oncogenic` | Cancer oncogenic signatures | CC-BY |
| `MSigDB_Immunologic` | Immune cell signatures | CC-BY |

## Input Formats

| Format | Extension | Required Data | Notes |
|--------|-----------|---------------|-------|
| Target AnnData | `.h5ad` | `X` (counts/normalized), `obs[<groupby>]` | Must contain clustered regions/annotations (e.g., `leiden`, `spatial_domain`). If missing during `--demo`, fast Leiden clustering is auto-generated. ssGSEA uses robust pseudobulk averages to prevent memory collapse. |

## CLI Reference

OmicsClaw provides the `oc` alias for unified skill execution (or use `python omicsclaw.py run`).

```bash
# General pathway enrichment (Enrichr, uses GO_Biological_Process by default)
oc run spatial-enrichment \
  --input ./data/clustered.h5ad \
  --output ./results/enrichment \
  --groupby spatial_domain

# Run GSEA using a specific MSigDB library and output to a custom directory
oc run spatial-enrichment \
  --input ./data/data.h5ad \
  --output ./results/gsea \
  --method gsea \
  --source KEGG_2021_Human \
  --species human

# Safe ssGSEA Demo (auto-generates required clusters and runs pseudobulk)
oc run spatial-enrichment --demo --method ssgsea --output /tmp/enrich_demo
```

## Example Queries

- "Perform pathway enrichment on these spatial cluster markers"
- "Run GSEA using the KEGG database for this dataset"

## Algorithm / Methodology

1. **Marker genes**: Run `sc.tl.rank_genes_groups` (Wilcoxon) to get per-cluster markers
2. **ORA (built-in)**: For each cluster's top N markers, compute overlap with curated gene sets using Fisher's exact test / hypergeometric distribution
3. **Optional GSEA**: When `gseapy` available, run `gp.enrichr()` or `gp.gsea()` against specified databases
4. **Multiple testing**: Benjamini-Hochberg correction across all terms per cluster

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── enrichment_dotplot.png
├── tables/
│   └── enrichment_results.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9
- `scipy` >= 1.7

**Optional**:
- `gseapy` — GSEA, Enrichr, and MSigDB access (graceful fallback to built-in ORA)

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — QC before enrichment
- `spatial-de` — Performs differential expression to gather markers

## Citations

- [GSEApy](https://gseapy.readthedocs.io/) — Python wrapper for GSEA/Enrichr
- [MSigDB](https://www.gsea-msigdb.org/) — Molecular Signatures Database
