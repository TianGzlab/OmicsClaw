---
name: bulkrna-ppi-network
description: >-
  Protein-protein interaction network analysis from DEG lists — STRING API query,
  graph construction, hub gene identification.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, PPI, STRING, network, hub-genes, protein-interaction]
requires: [numpy, pandas, matplotlib, scipy]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🕸️"
    trigger_keywords: [PPI, protein interaction, STRING, network, hub gene, interactome]
    allowed_extra_flags:
    - "--score-threshold"
    - "--species"
    - "--top-n"
    legacy_aliases: [bulk-ppi]
    saves_h5ad: false
    script: bulkrna_ppi_network.py
    param_hints: {}
    requires_preprocessed: false
---

# Bulk RNA-seq PPI Network Analysis

Protein-protein interaction (PPI) network construction from differentially expressed gene lists. Queries the STRING database API, builds interaction graphs, identifies hub genes by degree/betweenness centrality, and generates network visualizations.

## Core Capabilities

- Query STRING database for protein-protein interactions
- Built-in fallback: construct co-expression-based correlation network if STRING unavailable
- Graph centrality analysis: degree, betweenness, closeness, eigenvector centrality
- Hub gene identification (top-N by centrality)
- Force-directed network visualization with DE status coloring
- Export interaction edge lists and hub gene tables

## Why This Exists

- **Without it**: After identifying DEGs, researchers must separately query STRING via web browser, download edge lists, import into Cytoscape, compute centralities manually, and create publication-quality figures.
- **With it**: A single command goes from a gene list to a full PPI network analysis with hub genes, centrality metrics, and network visualization.
- **Why OmicsClaw**: Bridges the gap between DE analysis and systems biology by automating the STRING → graph → hub gene pipeline entirely in Python.

## Algorithm / Methodology

### STRING Interaction Query
1. Submit gene symbols to STRING API (`string-db.org/api`)
2. Filter interactions by combined score threshold (default ≥ 400)
3. Map STRING protein IDs back to gene symbols

### Graph Centrality
- **Degree**: Number of direct interaction partners
- **Betweenness**: Fraction of shortest paths passing through the node
- **Closeness**: Inverse of average shortest path length
- **Hub score**: Weighted combination of degree + betweenness

### Fallback: Correlation Network
When STRING is unavailable (no internet), builds a network from gene-gene Pearson correlations using the input expression matrix, with edges for |r| > threshold.

## Input Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Gene list | `.txt` | One gene symbol per line |
| DE results | `.csv` | Must contain `gene` column; optional `log2FoldChange`, `padj` |

## CLI Reference

```bash
python omicsclaw.py run bulkrna-ppi-network --demo
python omicsclaw.py run bulkrna-ppi-network --input de_results.csv --output results/
python bulkrna_ppi_network.py --input de_results.csv --output results/ --species 9606
```

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── ppi_network.png
│   └── hub_genes_barplot.png
├── tables/
│   ├── interaction_edges.csv
│   ├── node_centrality.csv
│   └── hub_genes.csv
└── reproducibility/
    └── commands.sh
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | — | Path to gene list (.txt) or DE results (.csv) |
| `--output` | — | Output directory |
| `--species` | `9606` | NCBI taxonomy ID (9606=human, 10090=mouse) |
| `--score-threshold` | `400` | Minimum STRING combined score |
| `--top-n` | `20` | Number of top hub genes to report |
| `--demo` | — | Run with demo data |

## Safety

- **Local-first**: STRING queries are the only external API call; all analysis is local.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.

## Integration with Orchestrator

**Chaining partners**:
- `bulkrna-de` — Upstream: provides DEG lists for network analysis
- `bulkrna-enrichment` — Parallel: pathway enrichment complements network topology
- `bulkrna-coexpression` — Parallel: WGCNA modules can be analyzed as sub-networks

## Citations

- [STRING](https://doi.org/10.1093/nar/gkaa1074) — Szklarczyk et al., NAR 2021

## Dependencies

**Required**: numpy, pandas, matplotlib
**Optional**: networkx (enhanced graph algorithms), requests (STRING API)

## Related Skills

- `bulkrna-de` — Differential expression upstream
- `bulkrna-enrichment` — Pathway enrichment analysis
- `bulkrna-coexpression` — Co-expression network analysis
