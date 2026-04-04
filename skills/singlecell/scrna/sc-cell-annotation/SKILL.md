---
name: sc-cell-annotation
description: >-
  Annotate cell types from preprocessed scRNA-seq data using marker scoring,
  CellTypist, PopV-style reference mapping, SingleR, or scmap through the
  shared Python/R backends.
version: 0.6.0
author: OmicsClaw
license: MIT
tags: [singlecell, annotation, celltypist, popv, singler, scmap]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--cluster-key"
      - "--method"
      - "--model"
      - "--reference"
    param_hints:
      markers:
        priority: "cluster_key"
        params: ["cluster_key"]
        defaults: {cluster_key: "leiden"}
        requires: ["cluster_labels_in_obs"]
        tips:
          - "--method markers: Fully implemented Python path using built-in marker scoring."
      celltypist:
        priority: "model"
        params: ["model"]
        defaults: {model: "Immune_All_Low"}
        requires: ["celltypist", "normalized_expression_matrix"]
        tips:
          - "--model: CellTypist model name or model file stem."
      popv:
        priority: "reference -> cluster_key"
        params: ["reference", "cluster_key"]
        defaults: {cluster_key: "leiden"}
        requires: ["labeled_reference_h5ad", "normalized_expression_matrix"]
        tips:
          - "--method popv: reference-mapped consensus annotation using a labeled H5AD reference provided via --reference."
      singler:
        priority: "reference"
        params: ["reference"]
        defaults: {reference: "HPCA"}
        requires: ["R_SingleR_stack"]
        tips:
          - "--method singler: SingleR reference-based annotation through the shared R bridge."
      scmap:
        priority: "reference"
        params: ["reference"]
        defaults: {reference: "HPCA"}
        requires: ["R_scmap_stack"]
        tips:
          - "--method scmap: scmap cluster projection through the shared R bridge."
    legacy_aliases: [sc-annotate]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "S"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - cell type annotation
      - annotate cells
      - celltypist
      - singler
      - popv
      - reference mapping
      - marker gene annotation
---

# Single-Cell Cell Annotation

## Why This Exists

- Without it: users hand-label clusters inconsistently or rely on opaque defaults.
- With it: annotation method, reference choice, and output columns are standardized.
- Why OmicsClaw: one wrapper unifies marker-based and reference-style entry paths.

## Core Capabilities

1. **Four annotation backends**: marker scoring, CellTypist, SingleR, and scmap.
2. **Unified label contract**: standardized `cell_type` output plus method provenance.
3. **Standard annotation gallery**: annotated UMAP, cluster-to-cell-type Sankey, and cell-type count bar plot.
4. **Figure-ready exports**: `figure_data/` CSVs plus a gallery manifest for downstream customization.
5. **Downstream-ready export**: annotated `processed.h5ad`, summary tables, report, result JSON, README, and notebook artifacts.

## Scope Boundary

Implemented methods:

1. `markers`
2. `celltypist`
3. `singler`
4. `scmap`

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | current direct input path |
| Demo | `--demo` | yes | bundled annotated-example fallback |

### Input Expectations

- Typical requirements: log-normalized expression and cluster labels such as `leiden`.
- Preferred matrix source: `adata.raw` when present and aligned; otherwise `adata.X`.
- Marker scoring needs a defensible grouping column.
- Reference-based methods need the selected model or reference resource to be available.

## Workflow

1. Validate required cluster/reference metadata.
2. Run the selected annotation backend.
3. Standardize output columns such as `cell_type` and `annotation_method`.
4. Export figures, tables, and the annotated AnnData object.
5. Record method/reference settings in `result.json`.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input <processed.h5ad> --method markers --cluster-key leiden --output <dir>

python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input <processed.h5ad> --method celltypist \
  --model Immune_All_Low --output <dir>

python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input <processed.h5ad> --method singler \
  --reference HPCA --output <dir>
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | annotation backend | `markers`, `celltypist`, `popv`, `singler`, or `scmap` |
| `--cluster-key` | grouping column | most important for `markers` and Sankey-style summaries |
| `--model` | CellTypist model selector | used only by `celltypist` |
| `--reference` | reference selector | H5AD reference path for `popv`; atlas selector for `singler` / `scmap` |

## Algorithm / Methodology

### `markers`

Current OmicsClaw marker-based annotation:

1. reads cluster labels from `cluster_key`
2. scores known marker patterns across clusters
3. writes standardized cell-type assignments back into `obs`

### `celltypist`

Current OmicsClaw CellTypist path:

1. selects the requested `model`
2. uses normalized expression from `adata.raw` when available, otherwise `adata.X`
3. writes per-cell predictions and standardized summary outputs

### `popv`

Current OmicsClaw PopV-style path:

1. loads a labeled reference H5AD from `--reference`
2. aligns overlapping genes between query and reference
3. projects query cells to reference label centroids
4. derives a cluster-level consensus label when `cluster_key` exists

### `singler` and `scmap`

Current OmicsClaw R-backed reference paths:

1. export expression data through the shared H5AD bridge
2. run the selected reference-based annotator in R
3. reimport labels into the standardized AnnData contract

Important implementation notes:

- `model` is the main CellTypist selector.
- `reference` is an OmicsClaw-level selector: a labeled H5AD for `popv`, or an atlas selector for the current SingleR / scmap path.
- If CellTypist input validation fails or the model cannot run, the wrapper falls back to `markers` and records both requested and actual methods.

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/manifest.json`
- `figure_data/manifest.json`
- `tables/annotation_summary.csv`
- `tables/cell_type_counts.csv`
- `reproducibility/commands.sh`

### Visualization Contract

The current standard Python gallery uses:

- `overview`: annotated UMAP colored by `cell_type`
- `diagnostic`: cluster-to-cell-type Sankey summary
- `supporting`: cell-type count bar plot

`figure_data/` is the stable hand-off layer for downstream restyling without rerunning annotation.

### What Users Should Inspect First

1. `report.md`
2. `figures/umap_cell_type.png`
3. `figures/sankey_<cluster_key>_to_cell_type.png`
4. `tables/annotation_summary.csv`
5. `processed.h5ad`

## Current Limitations

- `celltypist` can fall back to `markers` when the input matrix or requested model is not runnable in the current environment.
- `popv` currently expects `--reference` to point to a labeled H5AD reference rather than a symbolic atlas shortcut like `HPCA`.
- `singler` requires an R environment with `SingleR`, `celldex`, `SingleCellExperiment`, and `zellkonverter`.
- `scmap` requires an R environment with `scmap`, `celldex`, `SingleCellExperiment`, and `zellkonverter`.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.

## Safety And Guardrails

- Explain the selected annotation source explicitly: `cluster_key` for marker scoring, `model` for CellTypist, `reference` as a labeled H5AD for `popv`, or `reference` as an atlas selector for SingleR/scmap.
- Treat log-normalized expression as the expected matrix contract for all annotation paths.
- If the run falls back from `celltypist` to `markers`, state both the requested and executed methods instead of presenting marker labels as CellTypist output.
- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-cell-annotation-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-cell-annotation.md`.
