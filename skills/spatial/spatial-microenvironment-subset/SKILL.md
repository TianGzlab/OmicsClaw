---
name: spatial-microenvironment-subset
description: Load when extracting a niche / microenvironment subset around a center cell-type by spatial radius from a labelled spatial AnnData, producing a smaller AnnData of centers + their within-radius neighbours. Skip when running global tissue-domain detection (use spatial-domains) or for cross-condition comparison (use spatial-condition).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- spatial
- microenvironment
- niche
- subsetting
- neighbourhood
- visium
- xenium
requires:
- anndata
- scanpy
- numpy
- pandas
---

# spatial-microenvironment-subset

## When to use

The user has a labelled spatial AnnData (cell-type or domain labels in
`obs[--center-key]`) and wants to extract a niche around a chosen cell
population — i.e., the center cells PLUS every spot / cell within a
spatial radius of any center. Output is a downstream-ready AnnData
restricted to that microenvironment.

Single backend (radius-based KD-tree neighbourhood). Two radius modes:
`--radius-microns` (with `--microns-per-coordinate-unit` if your
coords aren't in microns) OR `--radius-native` (in the AnnData's
native coordinate units). Exactly one is required.

For *global* tissue-domain detection use `spatial-domains`. For
cross-condition niche comparison use `spatial-condition`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Labelled spatial AnnData | `.h5ad` with `obs[--center-key]` and `obsm["spatial"]` | yes (unless `--demo`) |
| Center label values | comma-separated string (`--center-values`) | yes |
| Radius | one of `--radius-microns` OR `--radius-native` | yes (mutually exclusive) |
| Optional target restriction | `--target-key` + `--target-values` | optional |

| Output | Path | Notes |
|---|---|---|
| Subset AnnData | `processed.h5ad` | rows = centers + within-radius neighbours; adds `obs["microenv_is_center"]`, `obs["microenv_role"]`, `obs["microenv_within_radius"]`, `obs["microenv_nearest_center"]`, `obs["microenv_distance_native"]`, plus `obs["microenv_distance_microns"]` only when `--microns-per-coordinate-unit` was supplied (`_lib/microenvironment.py:341/346`) |
| Selected observations | `tables/selected_observations.csv` | per-row role (center / neighbour) + distance |
| Centers retained | `tables/center_observations.csv` | always |
| Label composition | `tables/label_composition.csv` | label-prevalence before vs after subset |
| Run summary | `tables/selection_summary.csv` | always |
| Figure | `figures/microenvironment_selection.png` | spatial layout with selection overlay |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or build a demo.
2. Validate radius flags (`parser.error` on `≤ 0`); resolve `--microns-per-coordinate-unit` if needed.
3. Resolve center mask: rows where `obs[--center-key] ∈ --center-values` (comma-split).
4. Build a KD-tree on `obsm["spatial"]`; query each center for neighbours within radius.
5. Optionally restrict neighbour pool to `obs[--target-key] ∈ --target-values`.
6. Build the subset (centers + qualified neighbours; optionally drop centers via `--exclude-centers`).
7. Save subset AnnData with role + distance columns; emit composition / summary tables; render selection figure.

## Gotchas

- **All input + radius validation goes through `parser.error` (exit code 2).** `spatial_microenvironment_subset.py:403` for missing `--input`; `:405` for missing path; `:407` for non-positive `--microns-per-coordinate-unit`; `:409` for non-positive `--radius-microns`; `:411` for non-positive `--radius-native`. Wrappers expecting `ValueError` need to catch exit-2.
- **`--radius-microns` and `--radius-native` are mutually exclusive AND required.** `argparse.add_mutually_exclusive_group(required=True)` enforces it before the manual checks at `:409` / `:411`. Using neither hits a different `parser.error` (argparse-generated). Mixing the two raises argparse's standard "not allowed with" error.
- **`--microns-per-coordinate-unit` is needed when coords aren't in microns.** Visium typically already stores spatial coords in pixels; pass the platform-specific scale (e.g., `0.65` µm / pixel for high-res Visium) to make `--radius-microns` meaningful. Without it, the radius is treated as if coords were already in microns.
- **`--center-values` is required and `--center-key` is auto-resolvable.** `--center-values` always required (no default); `--center-key` defaults to None and the script auto-picks a sensible labelled obs column. For ambiguous AnnDatas, pass both explicitly.
- **`--exclude-centers` drops the center cells from the output.** Useful when you want to characterise *the niche around* a population without the population itself biasing downstream stats. By default centers ARE retained — `spatial_microenvironment_subset.py:461` invokes the helper with `include_centers=not args.exclude_centers`; `result.json["params"]["exclude_centers"]` records the raw flag at `:488`.
- **No raise for empty selection.** If the radius is too small or `--center-values` matches no rows, the script proceeds with an empty / center-only AnnData; `tables/selection_summary.csv` and `result.json["n_selected_observations"]` (line 195) record `0`. Always check before chaining downstream.

## Key CLI

```bash
# Demo (synthetic spatial with cell-type labels)
python omicsclaw.py run spatial-microenvironment-subset --demo --output /tmp/spatial_microenv_demo

# T-cell niche, 50 µm radius (Visium with 0.65 µm/pixel scale)
python omicsclaw.py run spatial-microenvironment-subset \
  --input annotated.h5ad --output results/ \
  --center-key cell_type --center-values "T cell,CD8+ T cell" \
  --radius-microns 50 --microns-per-coordinate-unit 0.65

# Tumor-infiltrating lymphocyte niche restricted to immune neighbours only
python omicsclaw.py run spatial-microenvironment-subset \
  --input annotated.h5ad --output results/ \
  --center-key cell_type --center-values "Tumor" \
  --target-key cell_type --target-values "T cell,B cell,Macrophage,NK cell" \
  --radius-microns 100 --microns-per-coordinate-unit 0.65

# Niche around domain "1" using native coords, exclude the centers
python omicsclaw.py run spatial-microenvironment-subset \
  --input annotated.h5ad --output results/ \
  --center-key spatial_domain --center-values "1" \
  --radius-native 50 --exclude-centers
```

## See also

- `references/parameters.md` — every CLI flag, radius / scale conventions
- `references/methodology.md` — radius selection guide; coordinate-unit semantics
- `references/output_contract.md` — `obs["microenv_is_center"]` / `obs["microenv_role"]` / `obs["microenv_distance_native"]` / `obs["microenv_distance_microns"]` schema
- Adjacent skills: `spatial-annotate` / `spatial-domains` (upstream — produce `obs[--center-key]` labels), `spatial-de` (downstream — DE on the niche subset between center vs neighbours), `spatial-communication` (downstream — L-R analysis restricted to a niche), `spatial-condition` (parallel — cross-condition niche comparison)
