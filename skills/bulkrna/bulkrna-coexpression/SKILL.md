---
name: bulkrna-coexpression
description: >-
  WGCNA-style weighted gene co-expression network analysis — module detection, soft thresholding, hub genes.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, coexpression, WGCNA, network, modules, hub-genes]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🕸️"
    trigger_keywords: [coexpression, WGCNA, gene network, co-expression modules, hub genes, gene modules]
    allowed_extra_flags:
      - "--min-module-size"
      - "--power"
    legacy_aliases: [bulk-wgcna]
    saves_h5ad: false
---

# Bulk RNA-seq Co-expression Network Analysis

WGCNA-style weighted gene co-expression network analysis. Detects gene modules via soft thresholding, topological overlap, and hierarchical clustering, then identifies hub genes per module.

## CLI Reference

```bash
python omicsclaw.py run bulkrna-coexpression --demo
python omicsclaw.py run bulkrna-coexpression --input <counts.csv> --output <dir>
python bulkrna_coexpression.py --input counts.csv --output results/
python bulkrna_coexpression.py --demo --output /tmp/coexpression_demo
python bulkrna_coexpression.py --input counts.csv --output results/ --power 6 --min-module-size 15
```

## Why This Exists

- **Without it**: Researchers must install the WGCNA R package, manually tune soft-thresholding power, interpret topological overlap matrices, and write custom scripts to extract hub genes from each module.
- **With it**: A single Python command runs the full WGCNA-style pipeline — soft threshold selection, TOM-based module detection, hub gene extraction — and produces publication-ready figures and tables.
- **Why OmicsClaw**: Implements the core WGCNA methodology in pure Python (numpy/scipy) with no R dependency, integrated into the OmicsClaw reporting framework with automatic scale-free topology fitting.

## Workflow

1. **Load**: Read a genes-by-samples raw count matrix (CSV with a `gene` column and sample columns).
2. **Transform**: Log2-transform counts (log2(x + 1)) and filter low-variance genes (keep top 80% by variance).
3. **Correlate**: Compute Pearson correlation matrix across all retained genes.
4. **Soft Threshold**: Test a range of soft-thresholding powers and select the first power achieving scale-free topology fit (R^2 > 0.8).
5. **Module Detection**: Compute adjacency matrix, topological overlap matrix (TOM), and apply hierarchical clustering with tree cutting to identify co-expression modules.
6. **Hub Genes**: For each module, rank genes by intra-module connectivity and report the top hub genes.
7. **Report**: Write markdown report, result.json, module assignment and hub gene tables, and a reproducibility script.

## Example Queries

- "Run WGCNA on my bulk RNA-seq data"
- "Find co-expression modules and hub genes"
- "Detect gene co-expression networks from my count matrix"
- "What soft threshold power should I use for my RNA-seq data?"
- "Identify hub genes in co-expression modules"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── scale_free_fit.png
│   ├── module_sizes.png
│   └── module_dendrogram.png
├── tables/
│   ├── module_assignments.csv
│   ├── hub_genes.csv
│   └── threshold_fit.csv
└── reproducibility/
    └── commands.sh
```

## Safety

- **Local-first**: All processing runs locally; no data is uploaded to external services.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.
- **Audit trail**: Parameters, method details, and input checksums are recorded in result.json.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked when user intent matches co-expression, WGCNA, gene network, or hub gene keywords.

**Chaining partners**:
- `bulkrna-de` -- Upstream: differentially expressed genes can be used as input
- `bulkrna-enrichment` -- Downstream: pathway/GO enrichment of module gene sets
- `bulkrna-qc` -- Upstream: count matrix QC

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--power` | auto | Soft-thresholding power (auto-selected if omitted) |
| `--min-module-size` | `10` | Minimum number of genes per module |

## Version Compatibility

Reference examples tested with: scipy 1.11+, pandas 2.0+, numpy 1.24+, matplotlib 3.7+

## Dependencies

**Required**: numpy, pandas, scipy, matplotlib

## Citations

- [WGCNA](https://doi.org/10.1186/1471-2105-9-559) -- Langfelder & Horvath, BMC Bioinformatics 2008
- [Scale-free topology](https://doi.org/10.2202/1544-6115.1128) -- Zhang & Horvath, Statistical Applications in Genetics and Molecular Biology 2005
- [Topological Overlap Matrix](https://doi.org/10.1073/pnas.0502024102) -- Yip & Horvath, BMC Bioinformatics 2007

## Related Skills

- `bulkrna-de` -- Differential expression analysis upstream
- `bulkrna-enrichment` -- Pathway enrichment of module gene sets downstream
- `bulkrna-qc` -- Count matrix QC upstream
