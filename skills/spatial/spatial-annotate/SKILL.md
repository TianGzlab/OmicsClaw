---
name: spatial-annotate
description: >-
  Cell type annotation for spatial transcriptomics data using Scanpy marker-gene
  overlap scoring, Tangram mapping, scANVI transfer, or CellAssign probabilistic
  models.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [spatial, annotation, cell-type, tangram, scanvi, cellassign, marker-genes,
  scanpy]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--batch-key"
    - "--cell-type-key"
    - "--cellassign-max-epochs"
    - "--cluster-key"
    - "--layer"
    - "--marker-n-genes"
    - "--marker-overlap-method"
    - "--marker-overlap-normalize"
    - "--marker-padj-cutoff"
    - "--marker-rank-method"
    - "--method"
    - "--model"
    - "--reference"
    - "--scanvi-max-epochs"
    - "--scanvi-n-hidden"
    - "--scanvi-n-layers"
    - "--scanvi-n-latent"
    - "--species"
    - "--tangram-device"
    - "--tangram-num-epochs"
    - "--tangram-train-genes"
    param_hints:
      marker_based:
        priority: "cluster_key → marker_rank_method → marker_n_genes / marker_padj_cutoff"
        params: ["cluster_key", "species", "marker_rank_method", "marker_n_genes",
          "marker_overlap_method", "marker_overlap_normalize", "marker_padj_cutoff"]
        defaults: {cluster_key: "leiden", species: "human", marker_rank_method: "wilcoxon",
          marker_n_genes: 50, marker_overlap_method: "overlap_count", marker_overlap_normalize: "reference"}
        requires: ["X_log_normalized", "cluster_labels"]
        tips:
        - "--marker-rank-method: Passed to `scanpy.tl.rank_genes_groups`; OmicsClaw
          defaults to `wilcoxon`."
        - "--marker-n-genes: Passed through as `top_n_markers` for `scanpy.tl.marker_gene_overlap`;
          set `0` to switch to adjusted-p-value marker selection."
        - "--marker-overlap-method / --marker-overlap-normalize: Passed to `scanpy.tl.marker_gene_overlap`;
          `reference` normalization preserves the old overlap / signature-size behavior."
        - "--marker-padj-cutoff: Only takes effect when `--marker-n-genes 0`, matching
          Scanpy's documented precedence."
      tangram:
        priority: "reference → cell_type_key → tangram_num_epochs → tangram_train_genes"
        params: ["reference", "cell_type_key", "tangram_num_epochs", "tangram_device",
          "tangram_train_genes"]
        defaults: {cell_type_key: "cell_type", tangram_num_epochs: 500, tangram_device: "auto",
          tangram_train_genes: 2000}
        requires: ["reference_h5ad", "X_log_normalized"]
        tips:
        - "--tangram-num-epochs: Passed to `tg.map_cells_to_space(..., num_epochs=...)`."
        - "--tangram-device: Passed to `tg.map_cells_to_space(..., device=...)`; `auto`
          resolves to CUDA, MPS, or CPU in that order."
        - "--tangram-train-genes: OmicsClaw wrapper control for the gene list passed
          into `tg.pp_adatas(..., genes=...)`; `0` means all shared genes."
      scanvi:
        priority: "reference → cell_type_key → batch_key/layer → scanvi_n_latent"
        params: ["reference", "cell_type_key", "batch_key", "layer", "scanvi_n_hidden",
          "scanvi_n_latent", "scanvi_n_layers", "scanvi_max_epochs"]
        defaults: {cell_type_key: "cell_type", layer: "counts", scanvi_n_hidden: 128,
          scanvi_n_latent: 10, scanvi_n_layers: 1, scanvi_max_epochs: 100}
        requires: ["reference_h5ad", "counts_or_raw"]
        tips:
        - "--layer / --batch-key: Passed to `SCVI.setup_anndata` / `SCANVI.setup_anndata`;
          use them when raw counts live outside `layers['counts']` or batch structure
          matters."
        - "--scanvi-n-hidden / --scanvi-n-latent / --scanvi-n-layers: Passed to the
          underlying `scvi.model.SCVI(...)` encoder-decoder."
        - "--scanvi-max-epochs: Current OmicsClaw wrapper uses this for SCVI pretraining,
          SCANVI finetuning, and query adaptation."
      cellassign:
        priority: "model/species → layer → batch_key → cellassign_max_epochs"
        params: ["model", "species", "layer", "batch_key", "cellassign_max_epochs"]
        defaults: {species: "human", layer: "counts", cellassign_max_epochs: 400}
        requires: ["counts_or_raw"]
        tips:
        - "--model: OmicsClaw wrapper path to a JSON marker-panel file; if omitted,
          built-in species signatures are used."
        - "--layer / --batch-key: Passed to `CellAssign.setup_anndata(..., layer=...,
          batch_key=...)`."
        - "--cellassign-max-epochs: Passed to `model.train(max_epochs=...)`."
    legacy_aliases: [annotate, spatial-cell-annotation]
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
    - label transfer
    - spatial annotation
    script: spatial_annotate.py
---

# 🏷️ Spatial Annotate

You are **Spatial Annotate**, the cell type annotation skill for OmicsClaw. Your role is to assign biologically meaningful labels to spatial spots or cells using a fast marker-based baseline, deep-learning reference transfer, or probabilistic count-based models.

## Why This Exists

- **Without it**: Users manually switch between Scanpy marker heuristics, Tangram, scANVI, and CellAssign with inconsistent data assumptions and poorly documented parameters
- **With it**: One command performs annotation, records the exact method-specific parameters, renders a standard Python narrative gallery, and exports plot-ready data for optional R-side refinement
- **Why OmicsClaw**: The current wrapper aligns method-specific flags with the underlying official APIs while keeping OmicsClaw-specific guardrails for matrix choice, reference validation, and result explanation

## Core Capabilities

1. **Marker-based annotation** (default): Scanpy `rank_genes_groups` + `marker_gene_overlap`, no external reference required
2. **Tangram transfer**: Deep-learning mapping from a scRNA-seq reference onto spatial coordinates
3. **scANVI transfer**: Semi-supervised variational label transfer with optional batch-aware setup
4. **CellAssign**: Marker-panel-based probabilistic annotation on raw counts
5. **Standard Python gallery**: Overview, supporting, diagnostic, and uncertainty plots rendered from a recipe-driven gallery layer
6. **Structured exports**: `report.md`, `result.json`, `processed.h5ad`, annotation tables, `figures/manifest.json`, `figure_data/`, and reproducibility commands

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| Spatial AnnData (preprocessed) | `.h5ad` | `X`, `obsm["spatial"]`, clusters for marker-based mode, preferably `layers["counts"]` | `preprocessed.h5ad` |
| Reference AnnData (Tangram / scANVI) | `.h5ad` | `X`, `obs["cell_type"]`, preferably `layers["counts"]` for scANVI | `reference_sc.h5ad` |
| Marker JSON (CellAssign, optional) | `.json` | `{cell_type: [marker genes...]}` | `tumor_panel.json` |
| Demo | n/a | `--demo` flag | Runs the default marker-based workflow on demo data |

### Input Matrix Convention

Different annotation methods make different assumptions about the input matrix:

| Method | Input Matrix | Rationale |
|--------|-------------|-----------|
| `marker_based` | `adata.X` (log-normalized) | `scanpy.tl.rank_genes_groups` and marker-overlap scoring compare continuous expression magnitudes across clusters |
| `tangram` | `adata.X` (log-normalized) for both spatial and reference | Tangram maps cells to space by matching expression profiles on a shared normalized scale |
| `scanvi` | `adata.layers["counts"]` or another raw-count layer | scVI/scANVI assume count-based likelihoods in `setup_anndata(..., layer=...)` |
| `cellassign` | `adata.layers["counts"]` or another raw-count layer | CellAssign models count data and computes size factors from the same raw matrix |

**Data layout requirement**: Preprocessing should preserve raw counts before normalization:

```python
adata.layers["counts"] = adata.X.copy()   # before normalize_total + log1p
adata.X = lognorm_expr                     # after normalize_total + log1p
```

If `layers["counts"]` is missing, count-based methods try `adata.raw` first and only fall back to `adata.X` with an explicit warning.

## Workflow

1. **Load**: Read the preprocessed spatial AnnData and any required reference / marker JSON.
2. **Validate**: Check matrix type, label columns, cluster labels, reference overlap, and method-specific parameter choices.
3. **Annotate**: Run Scanpy marker overlap, Tangram, scANVI, or CellAssign.
4. **Summarize**: Build annotation counts, optional cluster-to-cell-type mapping, confidence summaries, and visualization-ready outputs.
5. **Report and export**: Write `report.md`, `result.json`, `processed.h5ad`, tables, the standard Python gallery, plot-ready `figure_data/`, and the reproducibility bundle.

## CLI Reference

```bash
# Marker-based baseline (default)
oc run spatial-annotate \
  --input <preprocessed.h5ad> --output <dir>

# Marker-based tuning with Scanpy overlap scoring
oc run spatial-annotate \
  --input <preprocessed.h5ad> --method marker_based \
  --cluster-key leiden --marker-rank-method wilcoxon \
  --marker-n-genes 50 --marker-overlap-method overlap_count \
  --marker-overlap-normalize reference --output <dir>

# Marker-based p-adjusted marker selection (no fixed top-N)
oc run spatial-annotate \
  --input <preprocessed.h5ad> --method marker_based \
  --marker-n-genes 0 --marker-padj-cutoff 0.01 --output <dir>

# Tangram transfer
oc run spatial-annotate \
  --input <preprocessed.h5ad> --method tangram \
  --reference <reference_sc.h5ad> --cell-type-key cell_type \
  --tangram-num-epochs 500 --tangram-train-genes 2000 --output <dir>

# scANVI transfer
oc run spatial-annotate \
  --input <preprocessed.h5ad> --method scanvi \
  --reference <reference_sc.h5ad> --cell-type-key cell_type \
  --layer counts --batch-key sample_id \
  --scanvi-n-hidden 128 --scanvi-n-latent 10 --scanvi-max-epochs 100 \
  --output <dir>

# CellAssign with built-in marker panel
oc run spatial-annotate \
  --input <preprocessed.h5ad> --method cellassign \
  --species human --layer counts --cellassign-max-epochs 400 --output <dir>

# CellAssign with a custom marker-panel JSON
oc run spatial-annotate \
  --input <preprocessed.h5ad> --method cellassign \
  --model <marker_panel.json> --layer counts --output <dir>

# Demo mode (marker-based baseline)
oc run spatial-annotate --demo --output /tmp/annotate_demo

# Direct script entrypoint
python skills/spatial/spatial-annotate/spatial_annotate.py \
  --input <preprocessed.h5ad> --method marker_based --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

The current `spatial-annotate` implementation also writes a standard Python
gallery manifest at `figures/manifest.json` plus `figure_data/manifest.json`
for downstream custom visualization layers. A companion R template lives in
`skills/spatial/spatial-annotate/r_visualization/`.

## Example Queries

- "Assign cell types to my spatial tissue spots"
- "Use Tangram to transfer labels from my scRNA reference"
- "Run a batch-aware scANVI annotation with raw counts"
- "Use a custom marker panel with CellAssign"

## Algorithm / Methodology

### Marker-Based Annotation (default)

1. **Input**: `adata.X` (log-normalized expression) plus an existing cluster column such as `leiden`
2. **Marker ranking**: `scanpy.tl.rank_genes_groups(adata, cluster_key, method=..., n_genes=...)`
3. **Reference signature scoring**: `scanpy.tl.marker_gene_overlap(...)` compares cluster markers against built-in human or mouse marker signatures
4. **Annotation rule**: Each cluster is assigned the best-overlap cell type; the current OmicsClaw wrapper keeps an internal low-score floor to avoid overconfident labels

**Core tuning flags**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--cluster-key` | `leiden` | Cluster column to annotate |
| `--marker-rank-method` | `wilcoxon` | Passed to `scanpy.tl.rank_genes_groups` |
| `--marker-n-genes` | `50` | Passed as `top_n_markers`; use `0` to rely on adjusted p-value filtering instead |
| `--marker-overlap-method` | `overlap_count` | `overlap_count`, `overlap_coef`, or `jaccard` |
| `--marker-overlap-normalize` | `reference` | Scanpy normalization mode for `overlap_count`; `none` disables normalization |
| `--marker-padj-cutoff` | unset | Passed as `adj_pval_threshold` when `--marker-n-genes 0` |

### Tangram

1. **Input**: log-normalized spatial + reference AnnData objects
2. **Training-gene selection**: OmicsClaw derives a gene set for `tg.pp_adatas(..., genes=...)` from reference HVGs or all shared genes
3. **Mapping**: `tg.map_cells_to_space(..., mode="cells", num_epochs=..., device=...)`
4. **Projection**: `tg.project_cell_annotations(...)` creates per-spot cell-type predictions

**Core tuning flags**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--reference` | required | Reference scRNA-seq AnnData |
| `--cell-type-key` | `cell_type` | Label column in `reference.obs` |
| `--tangram-num-epochs` | `500` | Passed to `map_cells_to_space(..., num_epochs=...)` |
| `--tangram-device` | `auto` | Device string such as `cpu`, `cuda:0`, or `mps` |
| `--tangram-train-genes` | `2000` | OmicsClaw control for the gene list passed into `pp_adatas`; `0` means all shared genes |

### scANVI

1. **Input**: raw counts from `layer` plus a labelled reference AnnData
2. **Data registration**: `SCVI.setup_anndata(..., layer=..., batch_key=..., labels_key=...)`
3. **Reference model**: `scvi.model.SCVI(..., n_hidden=..., n_latent=..., n_layers=...)`
4. **Semi-supervised transfer**: `SCANVI.from_scvi_model(...)`, then query adaptation with `SCANVI.load_query_data(...)`
5. **Output**: predicted labels plus per-cell softmax confidence in `obs["scanvi_confidence"]`

**Core tuning flags**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--reference` | required | Reference scRNA-seq AnnData |
| `--cell-type-key` | `cell_type` | Label column in `reference.obs` |
| `--layer` | `counts` | Raw-count layer passed to `setup_anndata` |
| `--batch-key` | unset | Optional batch column passed to `setup_anndata` |
| `--scanvi-n-hidden` | `128` | Hidden-layer width in the SCVI backbone |
| `--scanvi-n-latent` | `10` | Latent-dimensionality parameter |
| `--scanvi-n-layers` | `1` | Number of encoder/decoder layers in the SCVI backbone |
| `--scanvi-max-epochs` | `100` | Current wrapper uses this for pretraining, finetuning, and query adaptation |

### CellAssign

1. **Input**: raw counts plus either a built-in species marker panel or a custom JSON marker panel
2. **Marker matrix**: OmicsClaw builds a binary marker matrix from the supplied cell-type signatures
3. **Size factors**: Computed from the same raw-count matrix used for CellAssign
4. **Registration**: `CellAssign.setup_anndata(..., size_factor_key=..., batch_key=..., layer=...)`
5. **Training**: `model.train(max_epochs=...)`

**Core tuning flags**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--model` | unset | OmicsClaw JSON marker-panel path; omit to use built-in signatures |
| `--species` | `human` | Built-in signature set when `--model` is not supplied |
| `--layer` | `counts` | Raw-count layer for CellAssign |
| `--batch-key` | unset | Optional batch covariate passed to `setup_anndata` |
| `--cellassign-max-epochs` | `400` | Passed to `model.train(max_epochs=...)` |

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── cell_type_spatial.png
│   ├── cell_type_umap.png
│   └── cell_type_barplot.png
│   ├── marker_overlap_heatmap.png              # marker_based
│   ├── annotation_confidence_spatial.png       # probabilistic methods
│   ├── annotation_confidence_histogram.png     # probabilistic methods
│   ├── annotation_probability_heatmap.png      # Tangram / scANVI / CellAssign
│   ├── custom/
│   │   └── annotation_spatial_publication.png  # optional R layer output
│   └── manifest.json
├── figure_data/
│   ├── annotation_spatial_points.csv
│   ├── annotation_umap_points.csv
│   ├── annotation_cell_type_counts.csv
│   ├── annotation_probabilities.csv            # probabilistic methods
│   ├── marker_overlap_scores.csv               # marker_based
│   └── manifest.json
├── tables/
│   ├── annotation_summary.csv
│   ├── cell_type_assignments.csv
│   ├── cluster_annotations.csv          # marker_based only
│   └── marker_overlap_scores.csv        # marker_based only
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── r_visualization.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution usually produces the
skill-native outputs plus `reproducibility/commands.sh` and an optional
`reproducibility/r_visualization.sh` helper that calls the bundled R template.

## Dependencies

**Required**: scanpy, anndata, numpy, pandas, scipy, matplotlib

**Optional**:
- `tangram-sc` — Tangram mapping
- `scvi-tools` — scANVI and CellAssign
- `torch` — acceleration backend for Tangram / scvi-tools

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Matrix guardrails**: Log-normalized expression is used only for `marker_based` / `tangram`; count-based methods require raw counts.
- **Audit trail**: Method-specific parameters are recorded in the report, `result.json`, and `reproducibility/commands.sh`.
- **Two-layer visualization design**: Python plots are the canonical standard gallery; the optional R layer consumes `figure_data/` for publication-style refinement without recomputing the science.
- **Reference validation**: Tangram and scANVI explicitly validate the requested label column and shared gene overlap before training.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — Prepare log-normalized expression, counts layer, clusters, and coordinates
- `spatial-domains` — Compare domain assignments with annotated cell types
- `spatial-communication` — Use labels for ligand-receptor or neighborhood communication analyses
- `spatial-deconv` — Use reference-aware deconvolution when spot-level mixtures are expected

## Citations

- [Scanpy `rank_genes_groups`](https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html)
- [Scanpy `marker_gene_overlap`](https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.marker_gene_overlap.html)
- [Tangram tutorial / API usage](https://tangram-sc.readthedocs.io/en/latest/tutorial_sq_link.html)
- [scvi-tools SCVI API](https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCVI.html)
- [scvi-tools SCANVI API](https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCANVI.html)
- [scvi-tools CellAssign API](https://docs.scvi-tools.org/en/stable/api/reference/scvi.external.CellAssign.html)
- [Tangram](https://doi.org/10.1038/s41592-021-01264-7) — Biancalani et al., *Nature Methods* 2021
- [scANVI](https://doi.org/10.15252/msb.20209620) — Xu et al., *Molecular Systems Biology* 2021
- [CellAssign](https://doi.org/10.1038/s41592-019-0529-1) — Zhang et al., *Nature Methods* 2019
