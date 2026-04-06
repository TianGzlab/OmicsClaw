---
name: spatial-preprocess
description: >-
  Load matrix-level spatial transcriptomics data (including raw_counts.h5ad
  from spatial-raw-processing), run the current OmicsClaw scanpy-standard preprocessing workflow,
  and export a downstream-ready AnnData with explicit effective QC parameters
  plus a standardized preprocessing visualization contract.
version: 0.5.0
author: OmicsClaw Team
license: MIT
tags: [spatial, preprocessing, QC, normalization, HVG, leiden, umap, visium, xenium]
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
    param_hints:
      scanpy_standard:
        priority: "tissue → min_genes/max_mt_pct/max_genes → n_top_hvg → n_pcs/n_neighbors → leiden_resolution"
        params: ["data_type", "species", "tissue", "min_genes", "min_cells", "max_mt_pct", "max_genes", "n_top_hvg", "n_pcs", "n_neighbors", "leiden_resolution", "resolutions"]
        defaults: {data_type: "generic", species: "human", min_genes: 0, min_cells: 0, max_mt_pct: 20.0, max_genes: 0, n_top_hvg: 2000, n_pcs: 30, n_neighbors: 15, leiden_resolution: 0.5}
        requires: ["raw_counts_in_X", "obsm.spatial_optional", "scanpy_pipeline"]
        tips:
          - "--tissue: OmicsClaw wrapper-level preset that fills QC defaults; reports also record the effective thresholds after preset resolution."
          - "--min-genes / --max-mt-pct / --max-genes: main QC thresholds controlling how aggressively low-quality spots are removed."
          - "--n-top-hvg: public Scanpy HVG selection budget passed to `pp.highly_variable_genes(..., flavor='seurat_v3', layer='counts')`."
          - "--n-pcs / --n-neighbors: public Scanpy graph-construction controls; OmicsClaw reports requested, computed, used, and suggested PCs separately."
          - "--leiden-resolution / --resolutions: public Leiden clustering resolution controls for the primary clustering and optional sweep."
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
      - spatial QC
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

You are **Spatial Preprocess**, the OmicsClaw skill for loading raw spatial
transcriptomics data and converting it into a downstream-ready AnnData under
the current `scanpy_standard` workflow. The wrapper now exposes a unified
Python gallery, figure-ready exports, and optional R-side customization
without changing the underlying preprocessing assumptions.

## Why This Exists

- **Without it**: users manually combine loading, QC, normalization, HVG selection, PCA, neighbors, and clustering with inconsistent defaults.
- **With it**: one command produces a standardized `processed.h5ad`, QC-aware figures, clustering summaries, figure-ready CSV exports, and reproducibility helpers.
- **Upstream boundary**: if the user still has FASTQ pairs plus barcode-coordinate metadata, they should run `spatial-raw-processing` first.
- **Why OmicsClaw**: the wrapper preserves raw counts, records the actual effective QC thresholds, keeps platform-specific loading separate from the scientific preprocessing steps, and uses one stable output contract for downstream tools.

## Core Capabilities

1. **Current workflow: `scanpy_standard`**: QC, normalization, `seurat_v3` HVG selection, PCA, neighbors, UMAP, and Leiden clustering.
2. **Multi-platform loading**: Visium directories / h5 / h5ad, Xenium zarr / h5ad, and converted `.h5ad` inputs for MERFISH / Slide-seq / seqFISH.
3. **QC filtering**: spot or cell filtering using `min_genes`, `min_cells`, `max_mt_pct`, and optional `max_genes`.
4. **Tissue-aware presets**: optional wrapper-level presets for common tissues such as brain, heart, tumor, and lung.
5. **Raw-count preservation**: raw counts are stored in both `adata.layers["counts"]` and `adata.raw` before normalization.
6. **Graph embedding**: PCA, neighbor graph, and UMAP.
7. **Clustering**: primary Leiden clustering plus optional multi-resolution sweeps.
8. **Standard Python gallery**: emits a recipe-driven preprocessing gallery with clustering overview, QC diagnostics, PCA guidance, and threshold-context panels.
9. **Figure-ready exports**: writes `figure_data/` CSVs plus a manifest so downstream tools can restyle the same preprocessing result without recomputing QC or clustering.
10. **Structured exports**: writes `report.md`, `result.json`, summary tables, reproducibility helpers, and an optional R visualization entrypoint.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| OmicsClaw raw spatial counts | `.h5ad` | `raw_counts.h5ad` emitted by `spatial-raw-processing` | `raw_counts.h5ad` |
| AnnData raw | `.h5ad` | count matrix in `X`; spatial coordinates recommended | `raw_visium.h5ad` |
| 10x Visium directory | directory | Space Ranger-style output | `visium_output/` |
| 10x feature matrix | `.h5` / `.hdf5` | filtered feature matrix | `filtered_feature_bc_matrix.h5` |
| Xenium zarr | `.zarr` or directory | Xenium export readable by `anndata.read_zarr` | `xenium_sample.zarr` |
| Converted MERFISH / Slide-seq / seqFISH | `.h5ad` | expression matrix, ideally with coordinates | `merfish_converted.h5ad` |
| Demo | n/a | `--demo` flag | built-in Visium-like demo |

## Upstream Boundary

If the user still has sequencing-level inputs such as FASTQ pairs plus an IDs
barcode-coordinate file and STAR reference files, this is **not** the correct
entry point. Run `spatial-raw-processing` first, then pass the resulting
`raw_counts.h5ad` into `spatial-preprocess`.

## Current Loader Behavior

| Data type | Current wrapper behavior |
|----------|--------------------------|
| `visium` | tries `sc.read_visium()` first, then 10x matrix fallbacks |
| `xenium` | supports `.h5ad` and `.zarr` |
| `slide_seq` | current wrapper expects converted `.h5ad` |
| `merfish` | current wrapper expects converted `.h5ad` |
| `seqfish` | current wrapper expects converted `.h5ad` |
| `generic` | expects `.h5ad` |

## Post-Preprocess Data Convention

After preprocessing, the processed object typically contains:

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
adata.obs["leiden_res_*"]      # optional multi-resolution results
```

## Tissue-Specific QC Presets

When `--tissue` is set, OmicsClaw auto-fills default QC thresholds. Explicit
CLI parameters still take precedence.

| Tissue | max_mt_pct | min_genes | max_genes | Notes |
|--------|------------|-----------|-----------|-------|
| pbmc | 5 | 200 | 2500 | low mitochondrial fraction in blood cells |
| brain | 10 | 200 | 6000 | higher complexity in neuronal tissue |
| heart | 50 | 200 | 5000 | cardiomyocytes are mitochondria-rich |
| tumor | 20 | 200 | 5000 | heterogeneous tissue composition |
| liver | 15 | 200 | 4000 | large hepatocytes |
| kidney | 15 | 200 | 4000 | mitochondria-active tubular cells |
| lung | 15 | 200 | 5000 | mixed epithelial and immune content |
| gut | 20 | 200 | 5000 | high epithelial turnover |
| skin | 10 | 200 | 4000 | keratinocyte-rich tissue |
| muscle | 30 | 200 | 5000 | elevated mitochondrial burden |

## Workflow

1. **Load**: detect platform type and load the dataset.
2. **QC metrics**: compute `n_genes_by_counts`, `total_counts`, and mitochondrial percentage.
3. **Filter**: apply `min_genes`, `min_cells`, `max_mt_pct`, and optional `max_genes`.
4. **Preserve counts**: store raw counts in `layers["counts"]` and `adata.raw`.
5. **Normalize**: run `normalize_total(target_sum=1e4)` followed by `log1p`.
6. **Select HVGs**: run `highly_variable_genes(..., flavor="seurat_v3", layer="counts")`.
7. **Embed**: scale HVGs, compute PCA, build neighbors, and compute UMAP.
8. **Cluster**: run the primary Leiden clustering and optional resolution sweep.
9. **Render the standard gallery**: build the OmicsClaw preprocessing gallery with clustering overview, QC maps, PCA variance guidance, and threshold-context panels.
10. **Export figure-ready data**: write `figure_data/*.csv` and `figure_data/manifest.json` for downstream customization.
11. **Export**: write summary tables, `report.md`, `result.json`, `processed.h5ad`, and reproducibility helpers.

## Visualization Contract

OmicsClaw treats `spatial-preprocess` visualization as a two-layer system:

1. **Python standard gallery**: the canonical preprocessing result layer. This is the default output users should inspect first.
2. **R customization layer**: an optional styling and publication layer that reads `figure_data/` and does not recompute QC, clustering, or embeddings.

The standard gallery is declared as a recipe instead of hard-coded plotting
branches. It reuses the shared `skills/spatial/_lib/viz` feature-map layer for
spatial and UMAP projections, while skill-local renderers handle preprocessing-
specific summaries such as PCA variance guidance and QC histograms.

Current gallery roles include:

- `overview`: primary Leiden clusters on tissue and UMAP
- `diagnostic`: QC metrics projected onto tissue coordinates
- `supporting`: cluster-size summary, PCA variance guidance, and optional resolution sweep
- `uncertainty`: QC metric distributions with effective threshold overlays

## CLI Reference

```bash
# Standard usage
oc run spatial-preprocessing --input <data.h5ad> --output <report_dir>

# Tissue-aware QC
oc run spatial-preprocessing \
  --input <data.h5ad> --output <report_dir> --tissue brain --species human

# Explicit QC thresholds
oc run spatial-preprocessing \
  --input <data.h5ad> --output <report_dir> \
  --min-genes 200 --max-mt-pct 15 --max-genes 5000

# Graph tuning
oc run spatial-preprocessing \
  --input <data.h5ad> --output <report_dir> \
  --n-top-hvg 3000 --n-pcs 30 --n-neighbors 15 --leiden-resolution 0.6

# Multi-resolution Leiden exploration
oc run spatial-preprocessing \
  --input <data.h5ad> --output <report_dir> --resolutions 0.4,0.6,0.8,1.0

# Explicit platform hint
oc run spatial-preprocessing \
  --input <xenium_sample.zarr> --output <report_dir> --data-type xenium

# Demo
oc run spatial-preprocessing --demo --output /tmp/spatial_preprocess_demo

# Direct script entrypoint
python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input <data.h5ad> --output <report_dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun. Direct script execution primarily produces the
skill-native outputs plus `reproducibility/commands.sh`.

## Example Queries

- "Preprocess my Visium dataset with standard QC and tell me which thresholds you will use first."
- "Load this Xenium data and generate a clustered h5ad."
- "Run spatial QC, preserve raw counts, and do a Leiden resolution sweep."

## Algorithm / Methodology

### `scanpy_standard`

1. **Tissue presets**: optionally fill QC defaults from the tissue preset table.
2. **QC metrics**: compute `n_genes_by_counts`, `total_counts`, and mitochondrial percentage using `qc_vars=["mt"]`.
3. **Filtering**: apply `min_genes`, `min_cells`, `max_mt_pct`, and optional `max_genes`.
4. **Counts preservation**: save raw counts into `adata.layers["counts"]` and `adata.raw`.
5. **Normalization**: run `sc.pp.normalize_total(target_sum=1e4)` followed by `sc.pp.log1p()`.
6. **HVG selection**: run `sc.pp.highly_variable_genes(..., flavor="seurat_v3", layer="counts")`.
7. **Scaling and PCA**: scale only the HVG subset and compute PCA.
8. **PC guidance**: suggest an informative PC count from cumulative explained variance, clamped to `[15, 30]`.
9. **Neighbors and UMAP**: build the neighbor graph and compute UMAP.
10. **Leiden clustering**: run the primary Leiden clustering plus optional extra resolutions.

**Core tuning flags**:

- `data_type`: wrapper-level loader hint, not a Scanpy science parameter.
- `species`: wrapper-level mitochondrial prefix selector.
- `tissue`: wrapper-level QC preset selector.
- `min_genes`, `min_cells`, `max_mt_pct`, `max_genes`: main QC thresholds.
- `n_top_hvg`: public Scanpy HVG budget.
- `n_pcs`: requested PCA dimensions before internal clipping by data shape.
- `n_neighbors`: public neighbor-graph size.
- `leiden_resolution`: public Leiden clustering resolution.
- `resolutions`: optional wrapper-level sweep over multiple Leiden resolutions.

> **Current OmicsClaw behavior**: reports include both the user-requested
> params and the actual effective params after preset application, plus
> requested / computed / used / suggested PC counts.

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── spatial_leiden.png
│   ├── umap_leiden.png
│   ├── qc_metrics_spatial.png
│   ├── cluster_size_barplot.png
│   ├── pca_variance_curve.png
│   ├── leiden_resolution_sweep.png        # if --resolutions was used
│   ├── qc_metric_distributions.png
│   └── manifest.json
├── figure_data/
│   ├── cluster_summary.csv
│   ├── qc_metric_distributions.csv
│   ├── preprocess_run_summary.csv
│   ├── pca_variance_ratio.csv
│   ├── multi_resolution_summary.csv       # if --resolutions was used
│   ├── preprocess_spatial_points.csv      # when spatial coordinates are available
│   ├── preprocess_umap_points.csv
│   └── manifest.json
├── tables/
│   ├── cluster_summary.csv
│   ├── qc_summary.csv
│   ├── pca_variance_ratio.csv
│   └── multi_resolution_summary.csv       # if --resolutions was used
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── environment.txt
    └── r_visualization.sh
```

The bundled optional R templates live under:

```text
skills/spatial/spatial-preprocess/r_visualization/
├── README.md
└── preprocess_publication_template.R
```

## Safety

- **Local-first**: all data processing stays local.
- **Raw preservation**: raw counts are preserved in both `adata.layers["counts"]` and `adata.raw`.
- **Audit trail**: reports, `result.json`, `figures/manifest.json`, and `figure_data/manifest.json` record effective QC and graph parameters plus visualization outputs.
- **Method-aware output**: the Python gallery is canonical; optional R styling consumes exported figure data and must not silently rerun preprocessing.
- **Platform-aware loading**: native vendor loaders are only used where the current wrapper actually supports them.

## Dependencies

**Required**:

- `scanpy`
- `anndata`
- `numpy`, `pandas`, `matplotlib`

**Common runtime companions**:

- `igraph`, `leidenalg`
- `squidpy`

**Optional (R)**:

- `ggplot2`

## Integration with Orchestrator

**Trigger conditions**:

- preprocess
- spatial preprocessing
- spatial QC
- normalization
- Leiden
- UMAP

**Chaining partners**:

- Often provides `processed.h5ad` to `spatial-domains`, `spatial-annotate`, `spatial-de`, `spatial-register`, and other downstream spatial skills

## Citations

- [Scanpy `normalize_total`](https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.normalize_total.html)
- [Scanpy `highly_variable_genes`](https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.highly_variable_genes.html)
- [Scanpy `neighbors`](https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.neighbors.html)
- [Scanpy `leiden`](https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.leiden.html)
