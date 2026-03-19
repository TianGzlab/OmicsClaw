---
name: bulkrna-enrichment
description: >-
  Pathway enrichment analysis for bulk RNA-seq — ORA and GSEA via GSEApy, with built-in hypergeometric fallback.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, enrichment, GSEA, ORA, GO, KEGG, Reactome, pathway]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🛤️"
    trigger_keywords: [bulk enrichment, pathway analysis, GSEA, ORA, GO enrichment, KEGG, bulk pathway]
---

# Bulk RNA-seq Pathway Enrichment

Pathway enrichment analysis for bulk RNA-seq differential expression results. Primary engine is GSEApy for ORA (Enrichr) and GSEA (pre-ranked); falls back to a built-in hypergeometric test with Benjamini-Hochberg FDR correction when GSEApy is not installed.

## Why This Exists

- **Without it**: Researchers must manually extract significant gene lists, format them for external enrichment tools, and cross-reference multiple pathway databases.
- **With it**: A single Python command runs ORA or GSEA on DE results, produces publication-ready bar and dot plots, and exports filtered enrichment tables ready for biological interpretation.
- **Why OmicsClaw**: Wraps the standard hypergeometric and rank-based enrichment approaches into the OmicsClaw reporting framework with automatic fallback when optional dependencies are unavailable.

## Workflow

1. **Load**: Read a DE results table (CSV with gene, log2FoldChange, pvalue, padj columns).
2. **Filter**: For ORA, extract significant genes at user-specified padj and log2FC cutoffs. For GSEA, rank all genes by a combined score.
3. **Enrich**: Test gene lists against pathway gene sets using hypergeometric ORA or rank-based GSEA.
4. **Correct**: Apply Benjamini-Hochberg multiple testing correction across all terms.
5. **Visualize**: Generate enrichment bar plot and dot plot of top enriched terms.
6. **Report**: Write markdown report, result.json, full and filtered enrichment tables, and a reproducibility script.

## CLI Reference

```bash
python bulkrna_enrichment.py --input <de_results.csv> --output <dir> --method ora
python bulkrna_enrichment.py --input <de_results.csv> --output <dir> --method gsea
python bulkrna_enrichment.py --demo --output /tmp/bulkrna_enrichment_demo
python bulkrna_enrichment.py --input <de.csv> --output <dir> --gene-set-file custom_sets.json
python omicsclaw.py run bulkrna-enrichment --demo
```

## Example Queries

- "Run pathway enrichment on my bulk RNA DE results"
- "Perform GSEA on this differential expression table"
- "Which GO terms are enriched in my upregulated genes?"
- "Run ORA with KEGG pathways on these DEGs"

## Algorithm / Methodology

1. **ORA (Over-Representation Analysis)**: For each gene set, compute a hypergeometric test p-value measuring the overlap between the user's significant gene list and the gene set, relative to the background gene count.
2. **GSEA (Gene Set Enrichment Analysis)**: Rank all genes by log2FC * -log10(pvalue), then for each gene set compute the mean rank compared to random gene sets via permutation testing.
3. **Multiple testing**: Benjamini-Hochberg correction across all tested terms.
4. **GSEApy integration**: When gseapy is installed, use its Enrichr and pre-ranked GSEA implementations. Otherwise, the built-in hypergeometric and rank-based methods provide equivalent core functionality.

## Input Formats

| Format | Extension | Required Columns | Example |
|--------|-----------|-----------------|---------|
| DE results CSV | `.csv` | `gene`, `log2FoldChange`, `pvalue`, `padj` | Output from `bulkrna-de` |

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── enrichment_barplot.png
│   └── enrichment_dotplot.png
├── tables/
│   ├── enrichment_results.csv
│   └── enrichment_significant.csv
└── reproducibility/
    └── commands.sh
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `ora` | `ora` or `gsea` |
| `--padj-cutoff` | `0.05` | Adjusted p-value significance threshold |
| `--lfc-cutoff` | `1.0` | Absolute log2 fold-change threshold (ORA gene filter) |
| `--gene-set-file` | None | Path to custom gene sets JSON (keys=term names, values=gene lists) |

## Dependencies

**Required**: numpy, pandas, scipy, matplotlib
**Optional**: gseapy (recommended; provides Enrichr and full GSEA functionality)

## Safety

- **Local-first**: All processing runs locally; no data is uploaded to external services.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.
- **Audit trail**: Parameters, method used (including fallback events), and input checksums are recorded in result.json.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked when user intent matches bulk RNA pathway enrichment keywords.

**Chaining partners**:
- `bulkrna-de` -- Upstream: differential expression to produce DE tables
- `bulkrna-coexpression` -- Parallel: co-expression modules for functional interpretation

## Citations

- [GSEApy](https://gseapy.readthedocs.io/) -- Python wrapper for GSEA/Enrichr
- [MSigDB](https://www.gsea-msigdb.org/) -- Molecular Signatures Database
- [Benjamini-Hochberg](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) -- Benjamini & Hochberg, JRSSB 1995
- [Subramanian et al.](https://doi.org/10.1073/pnas.0506580102) -- Gene set enrichment analysis, PNAS 2005

## Related Skills

- `bulkrna-de` -- Differential expression analysis upstream
- `bulkrna-coexpression` -- Co-expression network analysis
- `bulkrna-deconvolution` -- Cell type deconvolution of bulk samples
