---
name: spatial-annotate
description: Load when assigning per-spot cell-type labels on a spatial AnnData via marker-gene scoring
  or scRNA-reference mapping (Tangram / scANVI / CellAssign). Skip when computing spot-level cell-type
  proportions for multi-cell-per-spot platforms (use spatial-deconv); tissue-domain detection (use spatial-domains).
trigger: cell type annotation, annotate cell types, Tangram, scANVI, CellAssign, marker genes, label transfer, spatial annotation
tags:
- spatial
- annotation
- cell-type
- marker-based
- tangram
- scanvi
- cellassign
---

# spatial-annotate

## When to use

Assign discrete cell labels using marker overlap, Tangram, scANVI or CellAssign. Use spatial-deconv for proportions and spatial-domains for tissue regions.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-annotate")
data = read_input("input.h5ad")
data = library.annotate(data, cluster_key="leiden")
write_output(library.cell_type_counts(data), "tables/results.csv")
```

Run [examples/example_step.py](examples/example_step.py) through the step runner.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `annotate(adata, *, method: str='marker_based', reference=None, species: str='human', marker_genes: dict | None=None, random_state: int=0, **parameters)`

Annotate in place and return the same AnnData without file writes.

Marker and Tangram methods read log-normalized X. scANVI/CellAssign
require raw counts in the requested layer (normally counts), raw, or
explicitly selected X. Reference AnnData is copied before training.

:param adata: Spatial AnnData with normalized X and method-required labels/counts.
:param method: CLI default marker_based; tangram, scanvi or cellassign are optional.
:param reference: Labelled reference AnnData for Tangram/scANVI; None otherwise.
:param species: Human by default or mouse for built-in marker dictionaries.
:param marker_genes: Optional CellAssign marker mapping; None uses species markers.
:param random_state: Training seed, 0 by default; change to assess sensitivity.
:param parameters: Method keyword options in references/parameters.md. Defaults
    match the CLI, including cluster_key=leiden and n_marker_genes=50.
:returns: The same AnnData with cell_type labels and JSON run diagnostics.
:raises ValueError: Invalid method, species, missing reference or invalid counts.
:raises TypeError: Unknown method parameter.
:raises ImportError: Missing backend; use install_skill_deps for the named package.

### `run_info(adata, *, keep: bool=True) -> dict`

Read annotation counts, method parameters and cluster-marker scores.

:param adata: AnnData returned by annotate.
:param keep: True retains diagnostics; False removes them before CLI serialization.
:returns: Diagnostic dict, or an empty dict before analysis.

### `cell_type_counts(adata)`

Count cell labels and their percentages.

:param adata: AnnData with cell_type labels; expression values are not read.
:returns: DataFrame with cell_type, n_cells and proportion (percent).
:raises KeyError: Annotation labels are absent.

### `annotation_figure(adata)`

Plot discrete cell labels in spatial coordinates.

:param adata: Annotated spatial AnnData; reads coordinates and cell_type.
:returns: A matplotlib Figure without saving it.
:raises KeyError: Annotation labels are absent.

<!-- api:end -->

## Methods and parameters

Marker/Tangram methods read normalized X. scANVI/CellAssign validate raw integer counts. Reference methods take reference=AnnData; marker_genes applies only to CellAssign.
See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `annotate` requires a reference for Tangram/scANVI. `tables/cluster_annotations.csv` is marker-method output; probabilities are method-dependent.
- `run_info(keep=False)` removes library diagnostics before CLI serialization.

## Inputs and outputs

The library returns AnnData, DataFrames or Figures without file writes. The CLI
keeps reports, result.json, tables and conditional gallery outputs. See the
complete [output contract](references/output_contract.md) for filenames and conditions.

## CLI

```bash
python skills/spatial/spatial-annotate/spatial_annotate.py --input data.h5ad --output results/spatial-annotate
```

## See also

- [Methodology](references/methodology.md)
- [Parameters](references/parameters.md)
- [Output contract](references/output_contract.md)

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `scvi-tools`, `seaborn`, `tangram-sc`, `torch`
