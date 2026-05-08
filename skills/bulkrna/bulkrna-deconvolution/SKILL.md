---
name: bulkrna-deconvolution
description: >-
  Bulk RNA-seq cell type deconvolution using NNLS (built-in), with optional CIBERSORTx
  and MuSiC bridges.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, deconvolution, NNLS, CIBERSORTx, MuSiC, cell-type-proportion]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🧩"
    trigger_keywords: [bulk deconvolution, cell type proportion, NNLS, CIBERSORTx,
      bulk deconv, cell fraction]
    allowed_extra_flags:
    - "--reference"
    legacy_aliases: [bulk-deconv]
    saves_h5ad: false
    script: bulkrna_deconvolution.py
    param_hints: {}
    requires_preprocessed: false
---

# Bulk RNA-seq Cell Type Deconvolution

Estimate cell type proportions from bulk RNA-seq expression data using non-negative least squares (NNLS). Given a bulk count matrix and a cell type signature matrix (marker gene expression profiles), the skill solves for the mixture coefficients that best reconstruct each sample's expression profile and normalizes them to proportions summing to 1.

## CLI Reference

```bash
python omicsclaw.py run bulkrna-deconvolution --demo
python omicsclaw.py run bulkrna-deconvolution --input <counts.csv> --output <dir> --reference <signature.csv>
python bulkrna_deconvolution.py --input counts.csv --output results/ --reference signature.csv
python bulkrna_deconvolution.py --demo --output /tmp/deconv_demo
```

## Why This Exists

- **Without it**: Researchers must install and configure external deconvolution tools (CIBERSORTx web portal, MuSiC R package), each with its own data format requirements and authentication hurdles, just to get cell type proportions from bulk RNA-seq.
- **With it**: A single Python command runs NNLS-based deconvolution locally, produces publication-ready proportion charts, and exports per-sample cell type tables ready for downstream analysis.
- **Why OmicsClaw**: Wraps the mathematically principled NNLS approach into the OmicsClaw reporting framework with zero external dependencies beyond scipy, while documenting how to bridge to CIBERSORTx or MuSiC when higher accuracy is needed.

## Workflow

1. **Load**: Read the bulk count matrix (genes x samples CSV) and the cell type signature matrix (genes x cell_types CSV).
2. **Intersect**: Find shared genes between bulk data and signature matrix; subset both to shared features.
3. **Deconvolve**: For each sample, solve the NNLS problem `min ||Ax - b||` where A is the signature matrix, b is the sample expression vector, and x is the non-negative proportion vector.
4. **Normalize**: Scale each sample's proportion vector to sum to 1.
5. **Summarize**: Identify the dominant cell type per sample and compute mean proportions across all samples.
6. **Visualize**: Generate stacked bar chart, heatmap, and pie chart of cell type proportions.
7. **Report**: Write markdown report, result.json, proportion tables, and a reproducibility script.

## Example Queries

- "Deconvolve my bulk RNA-seq data to get cell type proportions"
- "Run NNLS deconvolution with this signature matrix"
- "Estimate cell type fractions from bulk expression"
- "What cell types are in my bulk RNA samples?"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── proportions_stacked.png
│   ├── proportions_heatmap.png
│   └── mean_proportions_pie.png
├── tables/
│   ├── proportions.csv
│   └── dominant_types.csv
└── reproducibility/
    └── commands.sh
```

## Safety

- **Local-first**: All computation runs locally via scipy NNLS; no data is uploaded to external services.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.
- **Audit trail**: Parameters, gene intersection size, and input checksums are recorded in result.json.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked when user intent matches bulk deconvolution, cell type proportion, or NNLS keywords.

**Chaining partners**:
- `bulkrna-qc` -- Upstream: count matrix QC
- `bulkrna-de` -- Upstream/parallel: differential expression identifies condition-specific cell type shifts
- `bulkrna-enrichment` -- Downstream: pathway enrichment on cell-type-specific gene sets

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | (required) | Path to bulk count matrix CSV (genes x samples) |
| `--output` | (required) | Output directory |
| `--reference` | (none) | Path to signature matrix CSV (genes x cell_types) |
| `--demo` | false | Run with built-in demo data |

## Signature Matrix Format

The reference signature matrix must be a CSV with:
- **Rows**: genes (first column is gene identifiers)
- **Columns**: cell types (each column header is a cell type name)
- **Values**: average expression levels for each gene in each cell type

## Bridging to External Tools

While NNLS provides a solid baseline, more sophisticated methods exist:

- **CIBERSORTx**: Upload signature and mixture matrices to the CIBERSORTx web portal for support-vector-regression-based deconvolution with batch correction. Requires free academic registration.
- **MuSiC**: R/Bioconductor package that uses multi-subject single-cell reference data with variance weighting. Requires R installation (not bundled).

## Version Compatibility

Reference examples tested with: scipy 1.11+, pandas 2.0+, numpy 1.24+, matplotlib 3.7+

## Dependencies

**Required**: numpy, pandas, scipy, matplotlib
**Optional**: none (NNLS is built into scipy)

## Citations

- [NNLS](https://doi.org/10.1137/1.9781611971217) -- Lawson & Hanson, Solving Least Squares Problems, 1995
- [CIBERSORTx](https://doi.org/10.1038/s41587-019-0114-2) -- Newman et al., Nature Biotechnology 2019
- [MuSiC](https://doi.org/10.1038/s41467-018-08023-x) -- Wang et al., Nature Communications 2019

## Related Skills

- `bulkrna-qc` -- Count matrix QC upstream
- `bulkrna-de` -- Differential expression analysis
- `bulkrna-enrichment` -- Pathway enrichment of gene sets downstream
- `spatial-deconvolution` -- Spatial transcriptomics deconvolution (CARD, Cell2Location)
