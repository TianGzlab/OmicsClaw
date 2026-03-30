---
name: spatial-annotate
description: >-
  Cell type annotation for spatial transcriptomics data using marker-based
  scoring, Tangram mapping, scANVI transfer, or CellAssign probabilistic models.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [spatial, annotation, cell-type, tangram, scanvi, cellassign, marker-genes]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--batch-key"
      - "--cell-type-key"
      - "--cluster-key"
      - "--layer"
      - "--method"
      - "--model"
      - "--reference"
      - "--species"
    param_hints:
      marker_based:
        priority: "cluster_key → species"
        params: ["cluster_key", "species"]
        defaults: {cluster_key: "leiden", species: "human"}
        requires: ["X_log_normalized"]
      tangram:
        priority: "reference → cell_type_key"
        params: ["reference", "cell_type_key", "species"]
        defaults: {cell_type_key: "cell_type", species: "human"}
        requires: ["reference_h5ad", "X_log_normalized"]
      scanvi:
        priority: "reference → cell_type_key → batch_key"
        params: ["reference", "cell_type_key", "batch_key", "layer"]
        defaults: {cell_type_key: "cell_type"}
        requires: ["reference_h5ad", "counts_or_raw"]
      cellassign:
        priority: "cell_type_key → layer"
        params: ["cell_type_key", "layer", "species"]
        defaults: {cell_type_key: "cell_type", species: "human"}
        requires: ["counts_or_raw"]
    legacy_aliases: [annotate]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🏷️"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - cell type annotation
      - annotate cell types
      - Tangram
      - scANVI
      - CellAssign
      - marker genes
---

# 🏷️ Spatial Annotate

You are **Spatial Annotate**, a specialised OmicsClaw agent for cell type annotation. Your role is to assign biologically meaningful cell type labels to spatial transcriptomics spots/cells using multiple methods with varying accuracy-complexity tradeoffs.

## Why This Exists

- **Without it**: Manual literature search for markers, inconsistent annotation across projects
- **With it**: One command annotates all spots with cell types, produces spatial maps and reports
- **Why OmicsClaw**: Unified interface across 4 methods with consistent reports, structured outputs, and wrapper-generated README/notebook guidance

## Workflow

1. **Load**: Read the preprocessed spatial AnnData and optional reference dataset.
2. **Validate**: Check that the required matrix representation and label columns exist for the selected method.
3. **Annotate**: Run marker scoring, Tangram transfer, scANVI transfer, or CellAssign probabilistic assignment.
4. **Summarize**: Generate annotation tables and spatial / UMAP visualizations when embeddings are available.
5. **Report and export**: Write `report.md`, `result.json`, `processed.h5ad`, tables, figures, and the reproducibility bundle.

## Core Capabilities

1. **Marker-based** (default, fast): No reference needed — scores cluster markers against built-in cell type signatures. Uses `adata.X` (log-normalized)
2. **Tangram**: Maps single-cell reference to spatial data via deep learning. Uses `adata.X` (log-normalized) for both reference and spatial
3. **scANVI**: Semi-supervised variational inference for label transfer. Uses `adata.layers["counts"]` (raw counts, NB model)
4. **CellAssign**: Probabilistic assignment using predefined marker gene panels. Uses `adata.layers["counts"]` (raw counts, NB model)

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (normalised), `layers["counts"]` (raw), `obsm["spatial"]`, clusters | `preprocessed.h5ad` |
| Reference (for tangram/scanvi) | `.h5ad` | `X`, `obs["cell_type"]` | `reference_sc.h5ad` |

### Input Matrix Convention

Different annotation methods have different statistical assumptions about the input expression data:

| Method | Input Matrix | Rationale |
|--------|-------------|-----------|
| `marker_based` | `adata.X` (log-normalized) | Marker scoring and Wilcoxon test operate on continuous expression where gene magnitudes are comparable |
| `tangram` | `adata.X` (log-normalized) | Both scRNA-seq and spatial must be on the same normalized scale for the mapping optimization |
| `scanvi` | `adata.layers["counts"]` (raw) | VAE generative model assumes negative-binomial / ZINB count likelihood |
| `cellassign` | `adata.layers["counts"]` (raw) | Probabilistic model assumes negative-binomial count likelihood; size factors computed from raw counts |

**Core principle**: Whether a method uses counts or normalized data depends on whether it has a count-based probabilistic model (NB/ZINB/GLM) internally.

**Data layout requirement**: Preprocessing must store raw counts before normalization:

```python
adata.layers["counts"] = adata.X.copy()   # before normalize_total + log1p
adata.X = lognorm_expr                     # after normalize_total + log1p
```

If `layers["counts"]` is missing, count-based methods (scanvi, cellassign) will fall back to `adata.raw` (if available) or `adata.X` with a warning.

## CLI Reference

```bash
# Marker-based (default, no reference needed)
python skills/spatial/spatial-annotate/spatial_annotate.py \
  --input <preprocessed.h5ad> --output <dir>

# Tangram transfer
python skills/spatial/spatial-annotate/spatial_annotate.py \
  --input <file> --method tangram --reference <sc_ref.h5ad> --output <dir>

# scANVI transfer
python skills/spatial/spatial-annotate/spatial_annotate.py \
  --input <file> --method scanvi --reference <sc_ref.h5ad> --output <dir>

# Demo
python skills/spatial/spatial-annotate/spatial_annotate.py --demo --output /tmp/annotate_demo

# Via CLI (using 'oc' short alias or 'python omicsclaw.py run')
oc run spatial-annotate --input <file> --output <dir>
oc run spatial-annotate --demo
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Assign cell types to my spatial tissue spots"
- "Use Tangram to map reference data to my slide"

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── umap_annotation.png
│   └── spatial_annotation.png
├── tables/
│   └── annotation_summary.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    └── commands.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution usually produces the
skill-native outputs plus `reproducibility/commands.sh`.

## Dependencies

**Required**: scanpy, anndata, numpy, pandas, scipy, matplotlib

**Optional**:
- `tangram-sc` — Tangram deep learning mapping
- `scvi-tools` — scANVI and CellAssign
- `singler` — SingleR reference-based (future)

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Reports follow the standard OmicsClaw reporting and disclaimer convention.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — QC before annotation
- `spatial-domains` — Regionalization after annotation
- `spatial-communication` — L-R scoring using annotated types

## Citations

- [Tangram](https://doi.org/10.1038/s41592-021-01264-7) — Biancalani et al., *Nature Methods* 2021
- [scANVI](https://doi.org/10.15252/msb.20209620) — Xu et al., *Mol Syst Biol* 2021
- [CellAssign](https://doi.org/10.1038/s41592-019-0529-1) — Zhang et al., *Nature Methods* 2019
