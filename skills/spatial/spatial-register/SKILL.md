---
name: spatial-register
description: >-
  Spatial registration and multi-slice alignment for spatial transcriptomics
  data using PASTE or STalign, with method-specific parameter hints,
  standardized aligned-coordinate outputs, and a unified registration
  visualization contract.
version: 0.5.0
author: OmicsClaw Team
license: MIT
tags: [spatial, registration, alignment, paste, stalign, multi-slice]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--method"
    - "--paste-alpha"
    - "--paste-dissimilarity"
    - "--paste-use-gpu"
    - "--reference-slice"
    - "--slice-key"
    - "--stalign-a"
    - "--stalign-image-size"
    - "--stalign-niter"
    - "--use-expression"
    param_hints:
      paste:
        priority: "slice_key/reference_slice → paste_alpha → paste_dissimilarity"
        params: ["slice_key", "reference_slice", "paste_alpha", "paste_dissimilarity",
          "paste_use_gpu"]
        defaults: {paste_alpha: 0.1, paste_dissimilarity: "kl", paste_use_gpu: false}
        requires: ["obsm.spatial", "obs.slice", "shared_genes", "X_expression"]
        tips:
        - "--slice-key: practical wrapper control; OmicsClaw requires a real slice
          label column instead of fabricating one."
        - "--paste-alpha: public PASTE weight between expression dissimilarity and
          spatial distance in `pairwise_align`."
        - "--paste-dissimilarity: public PASTE expression dissimilarity choice; the
          wrapper exposes the documented `kl` / `euclidean` options."
        - "--paste-use-gpu: public PASTE backend switch; only matters when a compatible
          Torch backend is available."
      stalign:
        priority: "slice_key/reference_slice → stalign_a → stalign_niter"
        params: ["slice_key", "reference_slice", "stalign_niter", "stalign_a", "stalign_image_size",
          "use_expression"]
        defaults: {stalign_niter: 2000, stalign_a: 500.0, stalign_image_size: 400,
          use_expression: false}
        requires: ["obsm.spatial", "obs.slice", "pairwise_two_slices", "X_expression_optional"]
        tips:
        - "--stalign-a / --stalign-niter: public STalign LDDMM controls that directly
          affect deformation smoothness and optimization depth."
        - "--stalign-image-size: current OmicsClaw wrapper rasterization resolution
          before calling LDDMM; this is wrapper-level, not the core scientific STalign
          parameter."
        - "--use-expression: current wrapper-level switch that uses PC1 of shared
          genes as image intensity instead of uniform weights."
    legacy_aliases: [register]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
      - python3
      env: []
      config: []
    emoji: "📐"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
    - kind: pip
      package: scanpy
      bins: []
    trigger_keywords:
    - spatial registration
    - slice alignment
    - coordinate alignment
    - PASTE
    - STalign
    - multi-slice
    script: spatial_register.py
---

# 📐 Spatial Register

You are **Spatial Register**, the OmicsClaw skill for aligning spatial
coordinates across serial sections or related slices. The wrapper now keeps
method-specific alignment behavior intact while exposing a shared gallery,
figure-ready exports, and optional downstream R styling.

## Why This Exists

- **Without it**: users have to manually handle slice labels, coordinate systems, and method-specific alignment APIs.
- **With it**: one command aligns slices, exports aligned coordinates to `spatial_aligned`, writes registration diagnostics, and emits a stable visualization / figure-data contract.
- **Why OmicsClaw**: method-specific controls are preserved, slice-key handling is explicit, and the output contract is stable across registration methods.

## Core Capabilities

1. **PASTE registration**: optimal-transport alignment using expression dissimilarity plus spatial distance.
2. **STalign registration**: pairwise diffeomorphic alignment through LDDMM.
3. **Explicit slice handling**: the wrapper can auto-detect common slice columns or accept `--slice-key`.
4. **Expression-aware alignment**: PASTE always uses expression; STalign can optionally use a wrapper-generated expression signal.
5. **Aligned coordinate export**: aligned coordinates are written to `adata.obsm["spatial_aligned"]`.
6. **Shift diagnostics**: OmicsClaw annotates per-observation coordinate displacement as `adata.obs["registration_shift_distance"]`.
7. **Standard Python gallery**: emits a recipe-driven registration gallery with before/after slice overlays, shift diagnostics, and per-slice summaries.
8. **Figure-ready exports**: writes `figure_data/` CSVs plus a manifest so downstream tools can restyle the same registration result without recomputing PASTE or STalign.
9. **Structured outputs**: writes `report.md`, `result.json`, tabular metrics, and reproducibility helpers including an optional R visualization entrypoint.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (multi-slice) | `.h5ad` | `X`, `obsm["spatial"]` or `obsm["X_spatial"]`, real slice labels in `obs[...]` | `serial_sections.h5ad` |
| Demo | n/a | `--demo` flag | runs `spatial-preprocess --demo`, then synthesizes two shifted slices |

## Method-Specific Input Requirements

| Method | Input requirements | Notes |
|--------|--------------------|-------|
| `paste` | expression matrix, spatial coordinates, slice labels, shared genes | current wrapper aligns all non-reference slices to a chosen reference |
| `stalign` | exactly 2 slices, spatial coordinates, optional expression-derived signal | current wrapper rasterizes coordinates into images and calls STalign LDDMM |

Important:

- PASTE is not a coordinates-only method; expression matters.
- STalign in the current wrapper requires exactly two slices.
- OmicsClaw does not fabricate synthetic slice labels for real input data; a real slice column is required.

## Workflow

1. **Load**: read the multi-slice AnnData.
2. **Validate**: confirm spatial coordinates and a real slice-label column exist.
3. **Run the selected backend**.
4. **Store aligned coordinates**: write `adata.obsm["spatial_aligned"]`.
5. **Annotate shift metrics**: compute `registration_shift_distance` and mark the reference slice in `adata.obs`.
6. **Render the standard gallery**: build the OmicsClaw registration gallery with before/after slice maps, shift diagnostics, and uncertainty panels.
7. **Export figure-ready data**: write `figure_data/*.csv` and `figure_data/manifest.json`.
8. **Report and export**: write summary tables, `report.md`, `result.json`, `processed.h5ad`, and reproducibility outputs.

## Visualization Contract

OmicsClaw treats `spatial-register` visualization as a two-layer system:

1. **Python standard gallery**: the canonical registration result layer.
2. **R customization layer**: an optional styling layer that reads `figure_data/` and does not rerun PASTE or STalign.

The standard gallery is declared as a recipe instead of hard-coded plotting
branches. It reuses the shared `skills/spatial/_lib/viz` feature-map layer for
slice overlays and shift projections, while skill-local renderers handle
registration-specific summaries such as per-slice displacement bars and shift
distance distributions.

Current gallery roles include:

- `overview`: slice labels before and after registration
- `diagnostic`: shift magnitude projected onto the aligned coordinate frame
- `supporting`: per-slice shift summary and method-reported disparity plots
- `uncertainty`: shift-distance distribution across slices

## CLI Reference

```bash
# Default alias used by OmicsClaw
oc run spatial-registration \
  --input <multi_slice.h5ad> --output <dir>

# PASTE with explicit reference and alpha
oc run spatial-registration \
  --input <multi_slice.h5ad> --method paste \
  --slice-key slice --reference-slice slice_1 \
  --paste-alpha 0.1 --paste-dissimilarity kl --output <dir>

# PASTE with GPU backend when available
oc run spatial-registration \
  --input <multi_slice.h5ad> --method paste \
  --paste-use-gpu --output <dir>

# STalign pairwise registration
oc run spatial-registration \
  --input <two_slices.h5ad> --method stalign \
  --slice-key slice --reference-slice slice_1 \
  --stalign-niter 3000 --stalign-a 800 --stalign-image-size 600 \
  --use-expression --output <dir>

# Demo mode
oc run spatial-registration --demo --output /tmp/register_demo

# Direct script entrypoint
python skills/spatial/spatial-register/spatial_register.py \
  --input <multi_slice.h5ad> --method paste --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun. Direct script execution primarily produces the
skill-native outputs plus `reproducibility/commands.sh`.

## Example Queries

- "Align my serial tissue sections using PASTE and explain alpha first."
- "Register these two slices with STalign and tell me what `a` changes."
- "Use `batch` as the slice key and align everything to sample A."

## Algorithm / Methodology

### PASTE

1. detect the slice column and choose a reference slice
2. intersect genes across slices
3. normalize each slice with `normalize_total` and `log1p`
4. run `paste.pairwise_align()` from each source slice to the reference
5. map source coordinates into the reference frame using the transport plan

**Core exposed controls**:

- `slice_key`: wrapper control selecting the obs column that defines slices
- `reference_slice`: fixed slice
- `paste_alpha`: public PASTE weight balancing expression dissimilarity and spatial distance
- `paste_dissimilarity`: public expression dissimilarity choice
- `paste_use_gpu`: public backend switch

### STalign

1. require exactly 2 slices
2. choose the reference slice and source slice
3. optionally derive a 1-D expression signal from PC1 of shared genes
4. rasterize the point clouds into images
5. run STalign LDDMM and warp source coordinates onto the target

**Core exposed controls**:

- `slice_key`
- `reference_slice`
- `stalign_niter`: public optimization-iteration control
- `stalign_a`: public smoothness / kernel bandwidth control
- `stalign_image_size`: wrapper-level rasterization resolution
- `use_expression`: wrapper-level switch using PC1 intensity instead of uniform intensity

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── slices_before.png
│   ├── slices_after.png
│   ├── registration_shift_map.png
│   ├── registration_shift_by_slice.png
│   ├── registration_disparities.png       # when method-reported disparities exist
│   ├── registration_shift_distribution.png
│   └── manifest.json
├── figure_data/
│   ├── registration_points.csv
│   ├── registration_shift_by_slice.csv
│   ├── registration_disparities.csv       # when method-reported disparities exist
│   ├── registration_run_summary.csv
│   └── manifest.json
├── tables/
│   ├── registration_summary.csv
│   └── registration_metrics.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── environment.txt
    └── r_visualization.sh
```

The bundled optional R templates live under:

```text
skills/spatial/spatial-register/r_visualization/
├── README.md
└── register_publication_template.R
```

## Safety

- **Local-first**: all registration stays local.
- **Real slice labels required**: the wrapper fails fast if no slice label column can be detected.
- **Audit trail**: reports, `result.json`, `figures/manifest.json`, and `figure_data/manifest.json` record only the parameters relevant to the selected backend plus the gallery outputs.
- **Method-aware explanation**: PASTE and STalign are not interchangeable and should not be described as such.
- **Canonical output boundary**: Python gallery is canonical; optional R styling consumes `figure_data/` and must not rerun registration.

## Dependencies

**Required**:

- `scanpy`
- `anndata`
- `scipy`
- `numpy`, `pandas`, `matplotlib`

**Optional (Python)**:

- `paste-bio` + `POT`
- `STalign` + `torch`

**Optional (R)**:

- `ggplot2`

## Integration with Orchestrator

**Trigger conditions**:

- spatial registration
- slice alignment
- coordinate alignment
- paste
- stalign

**Chaining partners**:

- `spatial-preprocess` — preprocessing before registration
- `spatial-integrate` — downstream integration after coordinate alignment

## Citations

- [PASTE](https://doi.org/10.1038/s41592-022-01459-6) — Zeira et al., *Nature Methods* 2022
- [STalign](https://doi.org/10.1038/s41467-023-43915-7) — Clifton et al., *Nature Communications* 2023
