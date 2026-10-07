---
name: spatial-microenvironment-subset
description: Load when extracting a niche / microenvironment subset around a center cell-type by spatial
  radius from a labelled spatial AnnData, producing a smaller AnnData of centers + their within-radius
  neighbours. Skip when running global tissue-domain detection (use spatial-domains); cross-condition
  comparison (use spatial-condition).
trigger: microenvironment, neighborhood subset, spatial radius, neighboring cells, nearby cells, tumor microenvironment, extract cells within 50 microns
tags:
- spatial
- microenvironment
- niche
- subsetting
- neighbourhood
- visium
- xenium
---

# spatial-microenvironment-subset

## When to use

Extract centers and nearby observations. Use spatial-domains for global regions and spatial-condition for condition comparisons.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-microenvironment-subset")
data = read_input("input.h5ad")
data = library.subset(data, center_key="cell_type", center_values=["Tumor"], radius_native=50)
write_output(library.selection_table(data), "tables/results.csv")
```

Run [examples/example_step.py](examples/example_step.py) through the step runner.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `subset(adata, *, center_values: list[str], center_key: str | None=None, radius_native: float | None=None, radius_microns: float | None=None, microns_per_coordinate_unit: float | None=None, data_type: str | None=None, include_centers: bool=True, target_key: str | None=None, target_values: list[str] | None=None)`

Return a new neighborhood AnnData; expression matrices remain unchanged.

:param adata: Labelled AnnData with spatial coordinates; X, layers and raw are sliced.
:param center_values: Labels defining centers, required as in the CLI.
:param center_key: Label column; None selects the first recognized label column.
:param radius_native: Positive coordinate-unit radius; default None requires radius_microns.
:param radius_microns: Positive micron radius, exclusive with radius_native.
:param microns_per_coordinate_unit: Explicit positive scale; None uses platform metadata.
:param data_type: Optional platform hint used to resolve units, as in the CLI.
:param include_centers: True retains centers regardless of the target-label filter.
:param target_key: Optional neighbor label column; None uses the center column.
:param target_values: Optional allowed neighbor labels; None admits all labels.
:returns: A new AnnData with role, distance and JSON diagnostics.
:raises ValueError: Invalid radius, labels, units, coordinates or an empty selection.

### `run_info(adata, *, keep: bool=True) -> dict`

Read selection counts and resolved coordinate units.

:param adata: AnnData returned by subset.
:param keep: True retains diagnostics; False removes them for CLI serialization.
:returns: Selection diagnostics, or an empty dict before analysis.

### `selection_table(adata)`

Return coordinates, center identities and nearest-center distances.

:param adata: AnnData returned by subset; expression values are not read.
:returns: One DataFrame row per selected observation.
:raises KeyError: Selection columns are absent.

### `selection_figure(adata)`

Plot selected centers and neighbors in coordinate units.

:param adata: AnnData returned by subset; reads coordinates and microenv_role.
:returns: A matplotlib Figure without saving it.
:raises KeyError: Selection roles are absent.

<!-- api:end -->

## Methods and parameters

KD-tree distances select observations near a center. Exactly one native or micron radius is required; micron distances require known coordinate units.
See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `subset` returns a copy and raises ValueError for missing centers or empty selections. `selection_table` adds micron distances only when a scale is known.
- `run_info(keep=False)` removes library diagnostics before CLI serialization.

## Inputs and outputs

The library returns AnnData, DataFrames or Figures without file writes. The CLI
keeps reports, result.json, tables and conditional gallery outputs. See the
complete [output contract](references/output_contract.md) for filenames and conditions.

## CLI

```bash
python skills/spatial/spatial-microenvironment-subset/spatial_microenvironment_subset.py --input data.h5ad --output results/spatial-microenvironment-subset --center-values Tumor --radius-native 50
```

## See also

- [Methodology](references/methodology.md)
- [Parameters](references/parameters.md)
- [Output contract](references/output_contract.md)

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`
