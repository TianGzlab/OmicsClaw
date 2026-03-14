---
name: spatial-preprocess
description: >-
  Load spatial transcriptomics data (Visium, Xenium, MERFISH, Slide-seq, generic h5ad),
  perform QC filtering, normalization, HVG selection, PCA, UMAP, and Leiden clustering.
version: 0.1.0
author: SpatialClaw
license: MIT
tags: [spatial, preprocessing, QC, normalization, clustering, visium, xenium]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🔬"
    homepage: https://github.com/SpatialClaw/SpatialClaw
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
2. **QC filtering**: Mitochondrial %, min genes/cells thresholds
3. **Normalization**: Library-size normalization + log1p
4. **HVG selection**: Seurat-flavored highly variable gene detection
5. **Embedding**: PCA, neighbor graph, UMAP
6. **Clustering**: Leiden community detection

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| AnnData raw | `.h5ad` | Count matrix in X | `raw_visium.h5ad` |
| 10x Visium dir | directory | Space Ranger output | `visium_output/` |
| 10x H5 | `.h5` | Filtered feature matrix | `filtered_feature_bc_matrix.h5` |
| Demo | n/a | `--demo` flag | Built-in synthetic data |

## Workflow

1. **Load**: Detect platform type and load data via `spatialclaw.spatial.loader`
2. **QC**: Compute metrics (n_genes, total_counts, pct_counts_mt), filter cells/genes
3. **Normalize**: `normalize_total` → `log1p`; store raw counts in `adata.raw`
4. **HVG**: Select highly variable genes
5. **Embed**: Scale → PCA → neighbors → UMAP
6. **Cluster**: Leiden clustering
7. **Report**: Write report.md, result.json, processed.h5ad, figures, reproducibility bundle

## CLI Reference

```bash
python skills/spatial-preprocess/spatial_preprocess.py \
  --input <data.h5ad> --output <report_dir> [--data-type visium] [--species human]

python skills/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/demo

python omicsclaw.py run preprocess --input <file> --output <dir>
python omicsclaw.py run preprocess --demo
```

## Example Queries

- "Preprocess my Visium dataset with standard QC metrics"
- "Load and normalize this h5ad spatial data for downstream tools"

## Algorithm / Methodology

1. **QC metrics**: `sc.pp.calculate_qc_metrics` with `qc_vars=["mt"]`
2. **Filter**: cells with `n_genes_by_counts >= min_genes`, genes in `>= min_cells` cells, `pct_counts_mt <= max_mt_pct`
3. **Normalize**: `sc.pp.normalize_total(target_sum=1e4)` → `sc.pp.log1p()`
4. **HVG**: `sc.pp.highly_variable_genes(n_top_genes=n_top_hvg, flavor="seurat")`
5. **Scale**: `sc.pp.scale(max_value=10)` on HVG subset
6. **PCA**: `sc.tl.pca(n_comps=n_pcs)`
7. **Neighbors**: `sc.pp.neighbors(n_neighbors=n_neighbors, n_pcs=n_pcs)`
8. **UMAP**: `sc.tl.umap()`
9. **Leiden**: `sc.tl.leiden(resolution=leiden_resolution)`

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
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required**: scanpy >= 1.9, anndata >= 0.11, squidpy >= 1.2, matplotlib, numpy, pandas

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.
- **Raw preservation**: Original counts saved in `adata.raw`

## Integration with Orchestrator

**Trigger conditions**: 
- Automatically invoked dynamically based on tool metadata and user intent matching.
- `.h5ad` file input, keywords: preprocess, QC, normalize, visium, xenium

**Chaining**: Output `processed.h5ad` feeds into all downstream spatial-* skills

## Citations

- [Scanpy](https://scanpy.readthedocs.io/) — analysis framework
- [Squidpy](https://squidpy.readthedocs.io/) — spatial extensions
- [Leiden algorithm](https://www.nature.com/articles/s41598-019-41695-z) — community detection
