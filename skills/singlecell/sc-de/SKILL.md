---
name: sc-de
description: >-
  Differential expression analysis for single-cell data — marker gene discovery
  using Wilcoxon, t-test, MAST compatibility, or DESeq2 pseudobulk analysis via R.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [singlecell, differential-expression, markers, Wilcoxon, MAST, pseudo-bulk]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧬"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - differential expression
      - marker genes
      - DE analysis
      - Wilcoxon
      - MAST
      - group comparison
      - pseudo-bulk
---

# 🧬 Single-Cell Differential Expression

You are **SC DE**, the differential expression and marker gene discovery skill for single-cell data. Your role is to identify genes that define cell populations or respond to experimental conditions.

## Why This Exists

- **Without it**: Users manually configure DE tests with inconsistent parameters, often overlooking fold-change artifacts in log-normalized single-cell data.
- **With it**: One command securely discovers robust markers per cluster or between any two biological groups using statistically sound methods.
- **Why OmicsClaw**: Standardized reporting includes Volcano plots, MA plots, and ranked marker tables out-of-the-box. Includes advanced pseudo-bulk testing for multi-sample designs.

## Core Capabilities

1. **Cluster-vs-rest markers**: Identify defining genes for every cell cluster (Wilcoxon, t-test, or MAST).
2. **Two-group pairwise comparison**: Compute DEGs between two conditions (e.g., Control vs Treatment) within specific cell types.
3. **Pseudo-bulk DE**: Aggregate counts across cells per sample/bio-rep for robust condition testing (DESeq2/edgeR integration).
4. **Comprehensive Visualisation**: Dotplots, Volcano plots, rank-genes group plots, and heatmaps.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (log1p normalized), `.raw` (raw counts needed for pseudo-bulk/MAST) | `annotated.h5ad` |

## Workflow

1. **Validate**: Verify if grouping variables exist and data matrices contain expected values.
2. **Execute**: Run selected DE statistical test.
3. **Filter**: Apply Log2FC and p-value Thresholds to identify significant up/down genes.
4. **Generate**: Save updated h5ad, generate plots (Volcano, dotplot).
5. **Report**: Write `report.md` with top hit summarization.

## CLI Reference

```bash
# Cluster vs Rest (FindAllMarkers)
python skills/singlecell/de/sc_de.py \
  --input <processed.h5ad> --groupby leiden --output <dir>

# Pairwise comparison within a cell type
python skills/singlecell/de/sc_de.py \
  --input <annotated.h5ad> --output <dir> --groupby condition \
  --group1 Treatment --group2 Control

# Pseudobulk DESeq2 through the R bridge
python skills/singlecell/de/sc_de.py \
  --input <annotated.h5ad> --output <dir> --method deseq2_r \
  --groupby condition --group1 Treatment --group2 Control \
  --sample-key sample_id --celltype-key cell_type

# Demo mode
python omicsclaw.py run sc-de --demo
```

## Algorithm / Methodology

### 1. Cluster vs Rest (Scanpy - Python)

**Goal:** Identify marker genes for each cluster against all other cells using Wilcoxon Rank-Sum.

```python
import scanpy as sc

# Ensure data is log1p normalized
adata = sc.read_h5ad('annotated.h5ad')

# Compute marker genes
sc.tl.rank_genes_groups(adata, groupby='cell_type', method='wilcoxon')

# Visualise results
sc.pl.rank_genes_groups(adata, n_genes=20, sharey=False)
sc.pl.rank_genes_groups_dotplot(adata, n_genes=4)
```

### 2. Pairwise Condition Testing (Scanpy - Python)

**Goal:** Compare two conditions (Treatment vs Control) constrained to a specific cell subset.

```python
import scanpy as sc

adata = sc.read_h5ad('annotated.h5ad')

# Filter to specific cell type
adata_sub = adata[adata.obs['cell_type'] == 'CD8 T cells'].copy()

# Run differential expression
sc.tl.rank_genes_groups(adata_sub, groupby='condition', 
                        groups=['Treatment'], reference='Control', method='wilcoxon')

# Extract result dataframe
import pandas as pd
result = sc.get.rank_genes_groups_df(adata_sub, group='Treatment')
sig_degs = result[(result['pvals_adj'] < 0.05) & (result['logfoldchanges'].abs() > 0.5)]
```

### 3. Pseudo-bulk DE (Python/R integration)

**Goal:** Address biological replicates properly by aggregating counts at the sample level before DE testing.

```python
import scanpy as sc
import decoupler as dc

adata = sc.read_h5ad('annotated.h5ad')

# Pseudo-bulking by Sample, condition, and cell_type
pdata = dc.get_pseudobulk(
    adata,
    sample_col='sample_id',
    groups_col='cell_type',
    mode='sum',
    min_cells=10,
    min_counts=1000
)

# Run DESeq2 or edgeR equivalent via PyDESeq2 or standard formulas
# (Pseudo-code for edgeR/DESeq2 workflow follows from pdata)
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--groupby` | `leiden` | Column in `.obs` defining the groups |
| `--method` | `wilcoxon` | Test: `wilcoxon`, `t-test`, `mast`, or `deseq2_r` |
| `--group1` | none | Pairwise group A (e.g. Treatment) |
| `--group2` | none | Pairwise group B (reference, e.g. Control) |
| `--sample-key` | `sample_id` | Sample/replicate column for `deseq2_r` |
| `--celltype-key` | `cell_type` | Cell type column for `deseq2_r` |

## Example Queries

- "Find marker genes for all clusters in this h5ad"
- "Compute differential expression between Tumor and Normal states for B cells"
- "Run a Wilcoxon test on the 'condition' column comparing DrugA to Vehicle"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── figures/
│   ├── marker_dotplot.png
│   ├── volcano_plot.png
│   └── rank_genes_groups.png
├── tables/
│   ├── markers_top.csv
│   └── de_full_statistics.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required**: scanpy >= 1.9, pandas, matplotlib
**Optional**: `rpy2` + `anndata2ri` + R packages `DESeq2`, `muscat`, `SingleCellExperiment`

## Runtime Notes

- `mast` is currently a compatibility option in the Python path and falls back to Wilcoxon.
- `deseq2_r` is the implemented replicate-aware pseudobulk backend and requires both `--group1` and `--group2`.

## Safety

- **Local-first**: No data upload. 
- **Disclaimer**: Every DE report includes the OmicsClaw disclaimer regarding valid statistical assertions.
- **Audit trail**: Log the exact p-value and Log2FC formulas applied in the bundle.

## Integration with Orchestrator

**Trigger conditions**:
- Expressions like "DE", "differential expression", "compare condition", "find markers".

**Chaining partners**:
- `sc-annotate`: Requires cell types to exist before performing meaningful condition comparisons.
- `sc-communication`: Identify DE ligands or receptors.

## Citations

- [Scanpy](https://scanpy.readthedocs.io/) — Wolf et al., Genome Biology 2018
- [Wilcoxon rank-sum](https://en.wikipedia.org/wiki/Mann–Whitney_U_test)
- [MAST](https://doi.org/10.1186/s13059-015-0844-5) — Finak et al., Genome Biology 2015
- [Decoupler (Pseudo-bulk)](https://doi.org/10.1093/bioinformatics/btac212) — Badia-i-Mompel et al., Bioinformatics 2022
