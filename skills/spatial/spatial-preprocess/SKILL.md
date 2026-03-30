---
name: spatial-preprocess
description: >-
  Load raw spatial transcriptomics data (Visium, Xenium, or h5ad inputs),
  run scanpy-standard QC, normalization, HVG selection, PCA, UMAP, and Leiden clustering,
  and produce a downstream-ready AnnData with reproducibility outputs.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [spatial, preprocessing, QC, normalization, leiden, umap, visium, xenium, h5ad]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--data-type"
      - "--leiden-resolution"
      - "--max-genes"
      - "--max-mt-pct"
      - "--min-cells"
      - "--min-genes"
      - "--n-neighbors"
      - "--n-pcs"
      - "--n-top-hvg"
      - "--resolutions"
      - "--species"
      - "--tissue"
    legacy_aliases: [preprocess]
    saves_h5ad: true
    requires_preprocessed: false
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
      - spatial preprocessing
      - QC
      - normalize
      - visium
      - xenium
      - merfish
      - slide-seq
      - load spatial data
      - leiden
      - umap
---

# 🔬 Spatial Preprocess

You are **Spatial Preprocess**, the foundation skill for OmicsClaw spatial analysis. Your role is to load raw spatial transcriptomics data, perform standard quality control and normalization, and produce a clean AnnData object ready for downstream spatial skills.

## Why This Exists

- **Without it**: Users manually stitch together loaders, QC thresholds, normalization, and clustering with inconsistent defaults.
- **With it**: One command loads the dataset, applies a standard preprocessing pipeline, saves figures and summaries, and emits a downstream-ready `processed.h5ad`.
- **Why OmicsClaw**: A single reproducible preprocessing contract across spatial workflows, with structured outputs, per-run README guidance, and notebook-based reproducibility in standard CLI runs.

## Core Capabilities

1. **Multi-platform loading**: Visium directories / h5 / h5ad, Xenium zarr / h5ad, and generic h5ad inputs.
2. **QC filtering**: Cell and gene filtering based on `min_genes`, `min_cells`, `max_mt_pct`, and optional `max_genes`.
3. **Tissue-aware presets**: Built-in QC presets for common tissues such as brain, heart, tumor, and lung.
4. **Normalization**: Library-size normalization plus `log1p`, while preserving raw counts in both `adata.layers["counts"]` and `adata.raw`.
5. **HVG selection**: `seurat_v3` highly variable gene selection using the preserved counts layer.
6. **Embedding**: PCA, neighbor graph construction, and UMAP.
7. **Clustering**: Primary Leiden clustering plus optional multi-resolution exploration.
8. **Reusable outputs**: Standard report, figures, tables, processed AnnData, README guidance, and reproducibility notebook in standard `oc run` executions.

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| AnnData raw | `.h5ad` | Count matrix in `X`; spatial coordinates recommended for downstream spatial plotting | `raw_visium.h5ad` |
| 10x Visium directory | directory | Space Ranger-style output | `visium_output/` |
| 10x feature matrix | `.h5` / `.hdf5` | 10x filtered feature matrix | `filtered_feature_bc_matrix.h5` |
| Xenium zarr | `.zarr` or directory | Xenium export readable by `anndata.read_zarr` | `xenium_sample.zarr` |
| Converted MERFISH / Slide-seq / seqFISH | `.h5ad` | Expression matrix; spatial coordinates strongly recommended | `merfish_converted.h5ad` |
| Demo | n/a | `--demo` flag | Built-in synthetic Visium-like dataset |

### Current Loader Behavior

- **Visium directories**: The current loader now tries `sc.read_visium()` first, then falls back to matrix loaders when needed.
- **Xenium**: Supported via `.h5ad` or `.zarr`.
- **MERFISH / Slide-seq / seqFISH**: In the current wrapper these modes are expected as converted `.h5ad` inputs rather than vendor-native raw bundles.
- **Spatial plots**: If spatial coordinates are absent, preprocessing can still run, but spatial figures and some downstream spatial workflows will be limited.

## Post-Preprocess Data Convention

After this skill completes, the processed object typically contains:

```text
adata.layers["counts"]         # preserved raw counts
adata.raw                      # raw-count snapshot before normalization
adata.X                        # log-normalized expression
adata.var["highly_variable"]   # HVG mask
adata.obsm["X_pca"]            # PCA embedding
adata.obsm["X_umap"]           # UMAP embedding
adata.obsp["connectivities"]   # neighbor graph
adata.obsp["distances"]        # neighbor distances
adata.obs["leiden"]            # primary Leiden clusters
adata.obs["leiden_res_*"]      # optional multi-resolution Leiden results
```

## Tissue-Specific QC Presets

When `--tissue` is set, OmicsClaw auto-fills default QC thresholds. Explicit CLI parameters still take precedence.

| Tissue | max_mt_pct | min_genes | max_genes | Notes |
|--------|------------|-----------|-----------|-------|
| pbmc | 5 | 200 | 2500 | Low mitochondrial fraction in blood cells |
| brain | 10 | 200 | 6000 | Higher gene complexity in neurons |
| heart | 50 | 200 | 5000 | Cardiomyocytes are mitochondria-rich |
| tumor | 20 | 200 | 5000 | Heterogeneous tissue composition |
| liver | 15 | 200 | 4000 | Large hepatocytes |
| kidney | 15 | 200 | 4000 | Tubular cells can be mitochondria-active |
| lung | 15 | 200 | 5000 | Mixed epithelial and immune content |
| gut | 20 | 200 | 5000 | High epithelial turnover |
| skin | 10 | 200 | 4000 | Keratinocyte-rich tissue |
| muscle | 30 | 200 | 5000 | Elevated mitochondrial burden |

## Workflow

1. **Load**: Detect platform type and load the dataset.
2. **QC**: Compute `n_genes_by_counts`, `total_counts`, and `pct_counts_mt`.
3. **Filter**: Remove low-quality cells and rarely detected genes.
4. **Preserve counts**: Store raw counts in `layers["counts"]` and `adata.raw`.
5. **Normalize**: Apply `normalize_total` and `log1p`.
6. **Select HVGs**: Run `seurat_v3` HVG selection on the counts layer.
7. **Embed**: Scale HVGs, compute PCA, build neighbors, and compute UMAP.
8. **Cluster**: Run primary Leiden clustering and optional multi-resolution exploration.
9. **Report and export**: Save figures, tables, report, processed AnnData, and reproducibility artifacts.

## CLI Reference

```bash
# Standard usage
oc run spatial-preprocess --input <data.h5ad> --output <report_dir>

# Tissue-aware QC
oc run spatial-preprocess \
  --input <data.h5ad> --output <report_dir> --tissue brain --species human

# Multi-resolution Leiden exploration
oc run spatial-preprocess \
  --input <data.h5ad> --output <report_dir> --resolutions 0.4,0.6,0.8,1.0

# Explicit platform hint
oc run spatial-preprocess \
  --input <xenium_sample.zarr> --output <report_dir> --data-type xenium

# Demo
oc run spatial-preprocess --demo --output /tmp/spatial_preprocess_demo

# Direct script entrypoint
python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input <data.h5ad> --output <report_dir> [--data-type generic]
```

Every successful standard `oc run` execution also writes a top-level `README.md`
and `reproducibility/analysis_notebook.ipynb` to make the output folder easier to inspect and rerun.

## Example Queries

- "Preprocess my Visium dataset with standard QC"
- "Load this Xenium data and generate a clustered h5ad"
- "Run spatial QC and normalization before domain identification"

## Algorithm / Methodology

### Scanpy Standard Pipeline

1. **Tissue presets**: Optionally auto-fill QC thresholds from the tissue preset table.
2. **QC metrics**: Compute `n_genes_by_counts`, `total_counts`, and mitochondrial percentage.
3. **Filtering**: Apply `min_genes`, `min_cells`, `max_mt_pct`, and optional `max_genes`.
4. **Counts preservation**: Save raw counts into `adata.layers["counts"]` and `adata.raw`.
5. **Normalization**: Run `sc.pp.normalize_total(target_sum=1e4)` followed by `sc.pp.log1p()`.
6. **HVG selection**: Run `sc.pp.highly_variable_genes(..., flavor="seurat_v3", layer="counts")`.
7. **Scaling and PCA**: Scale only the HVG subset and compute PCA.
8. **PC guidance**: Suggest an informative PC count from cumulative explained variance, clamped to `[15, 30]`.
9. **Neighbors and UMAP**: Build the neighbor graph and compute UMAP.
10. **Leiden clustering**: Run the primary Leiden clustering plus optional extra resolutions.

**Key parameters**:
- `min_genes`: Minimum detected genes per spot or cell. Default `0`, or preset-defined when `--tissue` is used.
- `max_mt_pct`: Maximum mitochondrial fraction. Default `20.0`, or preset-defined when `--tissue` is used.
- `max_genes`: Optional upper bound on detected genes per spot or cell. Default `0` meaning disabled.
- `n_top_hvg`: Number of HVGs to keep. Default `2000`.
- `n_pcs`: Requested PCA dimensions before internal clipping by data shape. Default `30` in the current CLI wrapper.
- `n_neighbors`: Neighbor graph size. Default `15`.
- `leiden_resolution`: Primary clustering resolution. Default `0.5` in the current CLI wrapper.
- `resolutions`: Optional comma-separated resolution sweep for exploratory clustering.
- `species`: Controls the mitochondrial prefix detection logic (`MT-` for human, `mt-` for mouse).

> **Current OmicsClaw behavior**: HVG selection uses the preserved counts layer,
> PCA is computed only on HVGs, and the neighbor graph uses at most 30 PCs even if
> a larger PCA is computed. This is the behavior that the wrapper executes today.

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── qc_violin.png
│   ├── umap_leiden.png
│   └── spatial_leiden.png
├── tables/
│   └── cluster_summary.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    └── commands.sh
```

### Output Files Explained

- `README.md`: Human-friendly entry point describing the run and where to look first.
- `report.md`: Narrative preprocessing summary with QC results, PC guidance, and clustering overview.
- `result.json`: Machine-readable summary for automation and downstream chaining.
- `processed.h5ad`: Downstream-ready AnnData containing normalized data, embeddings, graphs, and cluster labels.
- `figures/qc_violin.png`: QC metric overview across spots or cells.
- `figures/umap_leiden.png`: UMAP colored by primary Leiden clusters.
- `figures/spatial_leiden.png`: Spatial map colored by primary Leiden clusters when coordinates are available.
- `tables/cluster_summary.csv`: Cluster sizes for the primary Leiden result.
- `reproducibility/analysis_notebook.ipynb`: Notebook walkthrough for inspection and reruns in standard `oc run` outputs.
- `reproducibility/commands.sh`: Minimal rerun command with the same parameter set.

Additional files such as `reproducibility/requirements.txt` may appear when
environment capture is enabled, but they are not guaranteed for every run.

## Dependencies

**Required**:
- `scanpy` >= 1.9 - preprocessing, PCA, UMAP, and Leiden workflow
- `anndata` >= 0.11 - AnnData container support
- `squidpy` >= 1.2 - spatial plotting and ecosystem compatibility
- `numpy`, `pandas`, `matplotlib` - numerics, tables, and plotting

**Common runtime companions**:
- `igraph`, `leidenalg` - Leiden clustering backend used by the current wrapper

## Safety

- **Local-first**: All data processing stays local.
- **Disclaimer**: Reports inherit the OmicsClaw research-use disclaimer.
- **Audit trail**: Parameters and summary metrics are recorded in `result.json`.
- **Raw preservation**: Raw counts are preserved in both `adata.layers["counts"]` and `adata.raw`.
- **Transparent behavior**: The documented pipeline reflects the current wrapper behavior rather than only the idealized Scanpy workflow.

## Integration with Orchestrator

**Trigger conditions**:
- Raw or early-stage spatial inputs such as `.h5ad`, Visium directories, Xenium zarr, or 10x `.h5`
- User intents around preprocessing, QC, normalization, UMAP, Leiden, or preparing data for downstream spatial analysis

**Chaining partners**:
- `spatial-domains` - consumes `processed.h5ad` for tissue-domain identification
- `spatial-annotate` - uses embeddings and clusters for annotation workflows
- `spatial-de`, `spatial-communication`, `spatial-enrichment` - all expect a clean preprocessed AnnData

## Citations

- [Scanpy](https://scanpy.readthedocs.io/) - preprocessing and analysis framework
- [Squidpy](https://squidpy.readthedocs.io/) - spatial analysis ecosystem
- [Leiden algorithm](https://www.nature.com/articles/s41598-019-41695-z) - graph community detection
- [Luecken and Theis 2019](https://doi.org/10.15252/msb.20188746) - best practices for single-cell preprocessing that inform QC defaults
