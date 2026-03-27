---
name: spatial-preprocess
description: >-
  Load spatial transcriptomics data (Visium, Xenium, MERFISH, Slide-seq, generic h5ad),
  perform QC filtering, normalization, HVG selection, PCA, UMAP, and Leiden clustering.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [spatial, preprocessing, QC, normalization, clustering, visium, xenium]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--data-type"
      - "--leiden-resolution"
      - "--max-mt-pct"
      - "--min-cells"
      - "--min-genes"
      - "--n-neighbors"
      - "--n-pcs"
      - "--n-top-hvg"
      - "--species"
    legacy_aliases: [preprocess]
    saves_h5ad: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🔬"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
      - kind: pip
        package: squidpy
        bins: []
    trigger_keywords:
      - preprocess
      - QC
      - normalize
      - visium
      - xenium
      - merfish
      - slide-seq
      - load spatial data
      - clustering
      - leiden
      - umap
---

# 🔬 Spatial Preprocess

You are **Spatial Preprocess**, the foundation skill of OmicsClaw spatial analysis. Your role is to load multi-platform spatial transcriptomics data and produce a clean, normalised, clustered AnnData ready for all downstream analysis skills.

## Why This Exists

- **Without it**: Users manually write 40+ lines of Scanpy preprocessing code with inconsistent defaults
- **With it**: One command loads any spatial platform, runs QC, normalises, clusters, and produces a ready-to-analyse h5ad
- **Why OmicsClaw**: Standardised preprocessing ensures reproducibility across all downstream skills

## Workflow

1. **Calculate**: Prepare raw counts and assess QC metrics.
2. **Execute**: Run filtering, normalization, and feature selection.
3. **Assess**: Perform PCA and variance evaluation.
4. **Generate**: Save normalized matrices and compute default UMAP.
5. **Report**: Synthesize report with processing metadata and summaries.

## Core Capabilities

1. **Multi-platform loading**: Visium (directory/H5/H5AD), Xenium (Zarr/H5), MERFISH, Slide-seq, seqFISH, generic H5AD
2. **QC filtering**: Mitochondrial %, min/max genes thresholds, tissue-specific presets
3. **Normalization**: Library-size normalization + log1p, raw counts preserved in `layers['counts']`
4. **HVG selection**: Seurat v3 highly variable gene detection on raw counts
5. **Embedding**: PCA with data-driven component suggestion, neighbor graph, UMAP
6. **Clustering**: Leiden community detection with optional multi-resolution exploration
7. **Tissue presets**: Pre-configured QC thresholds for 10 tissue types

## Tissue-Specific QC Presets

When ``--tissue`` is specified, QC thresholds are automatically applied. Explicit parameters override preset values.

| Tissue | max_mt_pct | min_genes | max_genes | Notes |
|--------|-----------|-----------|-----------|-------|
| pbmc | 5% | 200 | 2500 | Low MT in blood cells |
| brain | 10% | 200 | 6000 | Neurons have many genes |
| heart | 50% | 200 | 5000 | Cardiomyocytes are MT-rich |
| tumor | 20% | 200 | 5000 | Heterogeneous tissue |
| liver | 15% | 200 | 4000 | Hepatocytes are large |
| kidney | 15% | 200 | 4000 | Tubular cells are MT-active |
| lung | 15% | 200 | 5000 | Mixed cell types |
| gut | 20% | 200 | 5000 | Epithelial turnover |
| skin | 10% | 200 | 4000 | Keratinocyte-rich |
| muscle | 30% | 200 | 5000 | High mitochondrial content |

## PC Selection Guidance

After PCA, the system automatically suggests an optimal number of PCs based on cumulative variance (85% threshold, clamped to [15, 30]). This is logged as a recommendation:

- **< 15 PCs**: Risk of underfitting (losing biological signal)
- **15-30 PCs**: Typical range for most spatial datasets
- **> 30 PCs**: Rarely needed; may include noise

## Multi-Resolution Clustering

Use ``--resolutions 0.4,0.6,0.8,1.0`` to explore multiple Leiden resolutions. All results are stored in ``adata.obs['leiden_res_X']`` columns and reported in the summary table.

**Resolution selection guidance:**
- **0.2-0.4**: Coarse clustering (few large clusters, broad tissue regions)
- **0.6-0.8**: Moderate (typical for spatial domain identification)
- **1.0-2.0**: Fine-grained (many small clusters, subtypes)

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| AnnData raw | `.h5ad` | Count matrix in X | `raw_visium.h5ad` |
| 10x Visium dir | directory | Space Ranger output | `visium_output/` |
| 10x H5 | `.h5` | Filtered feature matrix | `filtered_feature_bc_matrix.h5` |
| Demo | n/a | `--demo` flag | Built-in synthetic data |

## Workflow

1. **Load**: Detect platform type and load data via `skills.spatial._lib.loader`
2. **QC**: Compute metrics (n_genes, total_counts, pct_counts_mt), filter cells/genes
3. **Normalize**: `normalize_total` → `log1p`; store raw counts in `adata.raw`
4. **HVG**: Select highly variable genes
5. **Embed**: Scale → PCA → neighbors → UMAP
6. **Cluster**: Leiden clustering
7. **Report**: Write report.md, result.json, processed.h5ad, figures, reproducibility bundle

## CLI Reference

```bash
# Basic usage
python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input <data.h5ad> --output <report_dir> [--data-type visium] [--species human]

# With tissue preset
python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input <data.h5ad> --output <report_dir> --tissue brain --species human

# Multi-resolution exploration
python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input <data.h5ad> --output <report_dir> --resolutions 0.4,0.6,0.8,1.0

# Demo
python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/demo

# Via CLI (using 'oc' short alias or 'python omicsclaw.py run')
oc run spatial-preprocess --input <file> --output <dir>
oc run spatial-preprocess --demo
```

## Example Queries

- "Preprocess my Visium dataset with standard QC metrics"
- "Load and normalize this h5ad spatial data for downstream tools"

## Algorithm / Methodology

1. **Tissue presets** (optional): Apply tissue-specific QC thresholds if `--tissue` specified
2. **QC metrics**: `sc.pp.calculate_qc_metrics` with `qc_vars=["mt"]`
3. **Filter**: cells with `n_genes_by_counts >= min_genes` and `< max_genes`, genes in `>= min_cells` cells, `pct_counts_mt <= max_mt_pct`
4. **Preserve counts**: Store raw counts in `adata.layers['counts']` and `adata.raw`
5. **Normalize**: `sc.pp.normalize_total(target_sum=1e4)` → `sc.pp.log1p()`
6. **HVG**: `sc.pp.highly_variable_genes(n_top_genes=n_top_hvg, flavor="seurat_v3")`
7. **Scale**: `sc.pp.scale(max_value=10)` on HVG subset
8. **PCA**: `sc.tl.pca(n_comps=n_pcs)` + data-driven PC suggestion
9. **Neighbors**: `sc.pp.neighbors(n_neighbors=n_neighbors, n_pcs=min(n_comps, 30))`
10. **UMAP**: `sc.tl.umap()`
11. **Leiden**: `sc.tl.leiden(resolution=leiden_resolution)` + optional multi-resolution

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── qc_violin.png
│   └── umap_leiden.png
├── tables/
│   └── cluster_summary.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── checksums.sha256
```

## Dependencies

**Required**: scanpy >= 1.9, anndata >= 0.11, squidpy >= 1.2, matplotlib, numpy, pandas

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.
- **Raw preservation**: Original counts saved in both `adata.raw` and `adata.layers['counts']`

## Integration with Orchestrator

**Trigger conditions**: 
- Automatically invoked dynamically based on tool metadata and user intent matching.
- `.h5ad` file input, keywords: preprocess, QC, normalize, visium, xenium

**Chaining**: Output `processed.h5ad` feeds into all downstream spatial-* skills

## Citations

- [Scanpy](https://scanpy.readthedocs.io/) — analysis framework
- [Squidpy](https://squidpy.readthedocs.io/) — spatial extensions
- [Leiden algorithm](https://www.nature.com/articles/s41598-019-41695-z) — community detection
