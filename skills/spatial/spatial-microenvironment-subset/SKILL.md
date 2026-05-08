---
name: spatial-microenvironment-subset
description: >-
  Extract a local spatial microenvironment by selecting cells or spots within
  a physical radius of a center population, preserving coordinates and labels
  in a downstream-ready h5ad subset for tumor microenvironment, neighborhood,
  spatial communication, and related downstream analyses.
version: 0.1.0
author: OmicsClaw Team
license: MIT
tags:
- spatial
- microenvironment
- neighborhood
- radius
- subset
- communication
- xenium
- visium
metadata:
  omicsclaw:
    domain: spatial
    script: spatial_microenvironment_subset.py
    allowed_extra_flags:
    - "--center-key"
    - "--center-values"
    - "--target-key"
    - "--target-values"
    - "--exclude-centers"
    - "--radius-microns"
    - "--radius-native"
    - "--microns-per-coordinate-unit"
    legacy_aliases:
    - spatial-neighborhood-subset
    - spatial-proximity-subset
    - microenvironment
    - microenvironment subset
    - tumor microenvironment
    - neighborhood subset
    saves_h5ad: true
    requires_preprocessed: false
    trigger_keywords:
    - microenvironment
    - neighborhood subset
    - spatial radius
    - neighboring cells
    - nearby cells
    - tumor microenvironment
    - extract cells within 50 microns
    param_hints: {}
---

# Spatial Microenvironment Subset

Use this skill when the user wants to keep only the local neighborhood around a
center population before running downstream spatial analyses.

## Core Capabilities

1. Select center cells/spots by `adata.obs` label.
2. Keep all observations within a user-defined radius of those centers.
3. Optionally restrict neighbors to a second label filter.
4. Export a subset h5ad that preserves original coordinates and annotations.
5. Annotate selected observations with center/neighbor role and nearest-center distance.

## Expected Inputs

- AnnData with spatial coordinates in `obsm["spatial"]` or `obsm["X_spatial"]`
- At least one annotation column in `adata.obs` describing cell or spot identity
- Radius provided in either:
  - microns via `--radius-microns`
  - native coordinate units via `--radius-native`

## Practical Guidance

- Prefer `--radius-microns` when coordinate scaling is known or can be inferred.
- For Xenium-like inputs, coordinates are often already in microns.
- For custom or partially processed h5ad files, pass `--microns-per-coordinate-unit`
  if radius in microns cannot be inferred safely.
- Keep centers included by default when the subset will feed directly into
  `spatial-cell-communication`.

## Outputs

- `spatial_microenvironment_subset.h5ad`
- `tables/selected_observations.csv`
- `tables/center_observations.csv`
- `tables/label_composition.csv`
- `tables/selection_summary.csv`
- `figures/microenvironment_selection.png`

## Example

```bash
python skills/spatial/spatial-microenvironment-subset/spatial_microenvironment_subset.py \
  --input data/sample.h5ad \
  --output output/microenv \
  --center-key cell_type \
  --center-values tumor \
  --radius-microns 50
```
