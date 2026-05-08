---
name: sc-cell-annotation
description: >-
  Annotate cell types from normalized scRNA-seq data using marker scoring,
  CellTypist, PopV-style reference mapping, lightweight KNNPredict-style
  mapping, SingleR, or scmap through shared Python/R backends.
version: 0.9.0
author: OmicsClaw
license: MIT
tags: [singlecell, annotation, celltypist, popv, knnpredict, singler, scmap]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
    - "--manual-map"
    - "--manual-map-file"
    - "--cluster-key"
    - "--method"
    - "--model"
    - "--reference"
    - "--marker-file"
    - "--celltypist-majority-voting"
    - "--no-celltypist-majority-voting"
    - "--r-enhanced"
    param_hints:
      manual:
        priority: "cluster_key -> manual_map/manual_map_file"
        params: ["cluster_key", "manual_map", "manual_map_file"]
        defaults: {cluster_key: auto}
        requires: ["cluster_labels_in_obs"]
        tips:
        - "--method manual: explicit relabeling from user-provided cluster mappings."
        - "--manual-map example: `0=T cell;1,2=Myeloid`."
      markers:
        priority: "cluster_key -> marker_file"
        params: ["cluster_key", "marker_file"]
        defaults: {cluster_key: auto, marker_file: null}
        requires: ["normalized_expression", "cluster_labels_in_obs"]
        tips:
        - "--method markers: use when clusters already exist and you want a quick
          label proposal from known markers."
        - "Built-in markers cover blood (PBMC), brain, and general tissue cell types
          (human gene symbols)."
        - "For non-human organisms or specialized tissues, provide --marker-file markers.json."
        - "If ALL cells are 'Unknown', it means marker genes were not found — see
          Reference Data Guide below."
      celltypist:
        priority: "model -> celltypist_majority_voting"
        params: ["model", "celltypist_majority_voting"]
        defaults: {model: "Immune_All_Low", celltypist_majority_voting: false}
        requires: ["celltypist", "normalized_expression_matrix"]
        tips:
        - "--model: CellTypist model name or model file stem."
        - "--celltypist-majority-voting: optional neighborhood/cluster smoothing for
          CellTypist labels."
      popv:
        priority: "reference -> cluster_key"
        params: ["reference", "cluster_key"]
        defaults: {cluster_key: auto}
        requires: ["labeled_reference_h5ad", "normalized_expression_matrix"]
        tips:
        - "--method popv: official PopV path when possible, else lightweight reference
          mapping fallback."
      knnpredict:
        priority: "reference -> cluster_key"
        params: ["reference", "cluster_key"]
        defaults: {cluster_key: auto}
        requires: ["labeled_reference_h5ad", "normalized_expression_matrix"]
        tips:
        - "--method knnpredict: lightweight AnnData-first projection inspired by SCOP
          KNNPredict."
      singler:
        priority: "reference"
        params: ["reference"]
        defaults: {reference: "HPCA"}
        requires: ["R_SingleR_stack"]
        tips:
        - "--method singler: R SingleR path using celldex / ExperimentHub atlases
          or a labeled local H5AD reference."
      scmap:
        priority: "reference"
        params: ["reference"]
        defaults: {reference: "HPCA"}
        requires: ["R_scmap_stack"]
        tips:
        - "--method scmap: R scmap path using celldex / ExperimentHub atlases or a
          labeled local H5AD reference."
    legacy_aliases: [sc-annotate]
    saves_h5ad: true
    requires_preprocessed: true
    script: sc_annotate.py
---

# Single-Cell Cell Annotation

## Why This Exists

- Without it: users hand-label clusters inconsistently or trust opaque defaults.
- With it: annotation method, reference/model choice, label outputs, and figures are standardized.
- Why OmicsClaw: one wrapper unifies marker-based and reference-style annotation while preserving an AnnData-first workflow.

## Scope Boundary

Implemented methods:

1. `manual`
2. `markers`
3. `celltypist`
4. `popv`
5. `knnpredict`
6. `singler`
7. `scmap`

This skill annotates cells or clusters. It does not replace marker discovery or replicate-aware DE.

## Input Expectations

- Expected state: normalized expression in `adata.X`
- Typical upstream step: `sc-clustering`
- Typical downstream steps: `sc-markers`, `sc-de`, or interpretation/reporting
- Marker mode needs an existing cluster/label column; it will not auto-cluster anymore

## Public Parameters

- `--method`
- `--manual-map`
- `--manual-map-file`
- `--cluster-key`
- `--model`
- `--reference`
- `--marker-file`
- `--celltypist-majority-voting`

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/embedding_cell_type.png`
- `figures/embedding_cluster_vs_cell_type.png`
- `figures/cluster_to_cell_type_heatmap.png`
- `figures/cell_type_counts.png`
- `figures/embedding_annotation_score.png` when scores are available
- `figures/manifest.json`
- `figure_data/manifest.json`
- `tables/annotation_summary.csv`
- `tables/cell_type_counts.csv`
- `tables/cluster_annotation_matrix.csv`
- `reproducibility/commands.sh`

## What Users Should Inspect First

1. `report.md`
2. `figures/embedding_cell_type.png`
3. `figures/embedding_cluster_vs_cell_type.png`
4. `tables/annotation_summary.csv`
5. `processed.h5ad`

## Reference Data Guide

### Which method should I use?

| Scenario | Recommended method | Example |
|---|---|---|
| **PBMC / immune cells (human)** | `markers` (default) or `celltypist` | `--method markers` |
| **Immune cells (any tissue, human)** | `celltypist` | `--method celltypist --model Immune_All_Low.pkl` |
| **Mouse data** | `celltypist` with mouse model, or custom markers | `--method celltypist --model Mouse_Isocortex_Hippocampus.pkl` |
| **Specialized tissue (brain, lung, etc.)** | `celltypist` with tissue model, or `--marker-file` | `--method celltypist --model Human_Lung_Atlas.pkl` |
| **Have a labeled reference dataset** | `knnpredict` or `popv` | `--method knnpredict --reference ref.h5ad` |
| **R environment available** | `singler` or `scmap` | `--method singler --reference HPCA` |

### Custom marker file format

JSON format (recommended):
```json
{
  "T cell": ["CD3D", "CD3E", "CD4"],
  "B cell": ["MS4A1", "CD79A", "CD79B"],
  "Macrophage": ["CD68", "CD163"]
}
```

CSV format:
```
T cell,CD3D;CD3E;CD4
B cell,MS4A1;CD79A;CD79B
Macrophage,CD68;CD163
```

### CellTypist models

List all available models:
```python
import celltypist
celltypist.models.models_description()
```

Common models:
- `Immune_All_Low.pkl` / `Immune_All_High.pkl` — pan-immune (human)
- `Human_Lung_Atlas.pkl` — human lung
- `Cells_Intestinal_Tract.pkl` — human intestinal
- `Human_AdultAged_Hippocampus.pkl` — human brain
- `Mouse_Isocortex_Hippocampus.pkl` — mouse brain
- `Developing_Mouse_Brain.pkl` — developing mouse brain
- `Pan_Fetal_Human.pkl` — human fetal tissues

Download a specific model:
```python
celltypist.models.download_models(model="Immune_All_Low.pkl")
```

### Reference H5AD for knnpredict / popv

Your reference must be an H5AD file with:
- Normalized expression in `.X`
- A `cell_type` column in `.obs` (or another label column)

Sources for labeled references:
- [CZ CELLxGENE Census](https://cellxgene.cziscience.com/) — download tissue-specific datasets
- [Human Cell Atlas](https://www.humancellatlas.org/learn-more/data-access/) — curated atlases
- [Tabula Muris](https://tabula-muris.ds.czbiohub.org/) — mouse atlas

### Species and gene naming

- **Human** genes are typically UPPERCASE: `CD3D`, `MS4A1`, `EPCAM`
- **Mouse** genes are typically Title case: `Cd3d`, `Ms4a1`, `Epcam`
- The `markers` method will auto-detect species mismatch and attempt case-insensitive matching
- For best results with mouse data, use `celltypist` with a mouse-specific model or provide a custom `--marker-file` with mouse gene names

## Guardrails

- Treat `method` and its corresponding `model` / `reference` / `cluster_key` as the key scientific choices.
- Use normalized expression for public annotation workflows.
- If CellTypist falls back to `markers`, report both requested and executed methods.
- If `singler` / `scmap` use celldex atlases, remember they may still fail in restricted-network or empty-cache environments even when R packages are installed.

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | — | Input `.h5ad` file | required unless `--demo` |
| `--output` | str | — | Output directory | required |
| `--demo` | flag | off | Run with bundled PBMC3k data | — |
| `--method` | str | `markers` | Annotation method: `manual`, `markers`, `celltypist`, `popv`, `knnpredict`, `singler`, `scmap` | validated against METHOD_REGISTRY |
| `--model` | str | `Immune_All_Low` | CellTypist model name or file stem | celltypist only |
| `--reference` | str | `HPCA` | SingleR/scmap atlas key or path to labeled H5AD (popv/knnpredict) | — |
| `--cluster-key` | str | None | Cluster/label column for marker summaries; auto-detected when omitted | — |
| `--manual-map` | str | None | Inline cluster-to-label mapping, e.g. `0=T cell;1,2=Myeloid` | manual only |
| `--manual-map-file` | str | None | Path to mapping file (json/csv/tsv/txt) | manual only |
| `--marker-file` | str | None | Path to custom marker gene file (JSON or CSV) | markers only |
| `--celltypist-majority-voting` | flag | off | Enable CellTypist neighborhood majority-voting smoothing | celltypist only |
| `--species` | str | `Human` | SCSA species filter (`Human`/`Mouse`) | scsa only |
| `--tissue` | str | `All` | SCSA tissue filter (e.g. `Blood`, `Brain`, `All`) | scsa only |
| `--scsa-foldchange` | float | 1.5 | SCSA DE fold-change threshold | scsa only |
| `--scsa-pvalue` | float | 0.05 | SCSA DE p-value threshold | scsa only |
| `--r-enhanced` | flag | off | Also render R Enhanced ggplot2 figures | — |

## R Enhanced Plots

Activated by `--r-enhanced`. Files written to `figures/r_enhanced/`.

| Renderer | Output file | figure_data CSV | Plot description | Required R packages |
|----------|-------------|-----------------|------------------|---------------------|
| `plot_embedding_discrete` | `r_embedding_discrete.png` | `annotation_embedding_points.csv` | UMAP/embedding colored by annotated cell types | ggplot2 |
| `plot_embedding_feature` | `r_embedding_feature.png` | `annotation_embedding_points.csv` | UMAP/embedding colored by annotation confidence score | ggplot2 |
| `plot_cell_barplot` | `r_cell_barplot.png` | `cell_type_counts.csv` | Bar chart of cell type counts | ggplot2 |
| `plot_cell_proportion` | `r_cell_proportion.png` | `cell_type_counts.csv` | Stacked proportion bar chart per sample or cluster | ggplot2 |
| `plot_cell_sankey` | `r_cell_sankey.png` | `cluster_annotation_matrix.csv` | Sankey/alluvial diagram from cluster to cell type | ggplot2, ggalluvial |

## Workflow Position

**Upstream:** sc-clustering
**Downstream:** sc-markers, sc-de, sc-cell-communication, sc-differential-abundance
