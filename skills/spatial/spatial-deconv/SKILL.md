---
name: spatial-deconv
description: Load when deconvolving spot-level cell-type proportions on a Visium-style spatial AnnData
  using a labelled scRNA reference (FlashDeconv / Cell2location / RCTD / DestVI / Tangram / others). Skip
  when each spot is a single cell already (Xenium / MERFISH) (use spatial-annotate); tissue-domain detection
  (use spatial-domains).
trigger: cell type deconvolution, spatial deconvolution, cell proportion, cell type proportion, cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, CARD
tags:
- spatial
- deconvolution
- cell2location
- rctd
- destvi
- stereoscope
- tangram
- spotlight
- card
- flashdeconv
---

# spatial-deconv

## When to use

Estimate cell-type proportions for spatial spots using a labelled single-cell
reference. Use spatial-annotate for discrete labels and spatial-domains for
tissue regions. Every method requires a reference; the CLI default is cell2location.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
spatial = read_input("spatial.h5ad")
reference = read_input("reference.h5ad")
library = load_skill("spatial-deconv")
library.deconvolve(spatial, reference=reference, method="flashdeconv", random_state=0)
write_output(library.proportions(spatial), "tables/proportions.csv")
```

[examples/example_step.py](examples/example_step.py) uses an explicit synthetic
reference and verifies known stripe identities; it is not a real-tissue benchmark.
It sets lambda_spatial=10 for the small grid; the CLI default remains 5000.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `deconvolve(adata, *, reference, method: str='cell2location', cell_type_key: str='cell_type', random_state: int=0, **parameters)`

Estimate proportions in place and return the same spatial AnnData.

Count models read layers['counts'], raw or X in that order. FlashDeconv,
Tangram and SPOTlight read nonnegative X. Reference data are copied.
RCTD, SPOTlight and CARD retain their temporary R bridges; their wrappers
do not expose a seed and results vary between runs.

:param adata: Spatial AnnData; input expression is retained.
:param reference: Required labelled reference AnnData; load it with read_input.
:param method: CLI default cell2location; flashdeconv, rctd, destvi,
    stereoscope, tangram, spotlight and card are also supported.
:param cell_type_key: Reference label column, CLI default cell_type.
:param random_state: Seed for FlashDeconv/Tangram and scvi training, default 0.
:param parameters: Method options in references/parameters.md, with CLI
    prefixes removed; omitted options keep their CLI defaults.
:returns: The same AnnData with deconvolution_<method>, labels and JSON diagnostics.
:raises ValueError: Invalid method, expression, reference labels or backend proportions.
:raises TypeError: Reference is not AnnData or a method option is unknown.
:raises ImportError: A backend is missing; use install_skill_deps for its named package.

### `run_info(adata, *, keep: bool=True) -> dict`

Read method settings, reference overlap and result diagnostics.

:param adata: AnnData returned by deconvolve.
:param keep: True retains diagnostics; False removes them before CLI serialization.
:returns: Diagnostic dict with matrix_sources, seed (None for R wrappers)
    and optional CARD refinement tables.

### `proportions(adata, *, method: str | None=None)`

Return stored proportions with observation and cell-type identifiers.

:param adata: AnnData returned by deconvolve; expression values are not read.
:param method: None infers a sole stored method; specify it after multiple analyses.
:returns: A DataFrame indexed by observation, with one column per reference label.
:raises ValueError: No unique method can be inferred or label metadata are missing.

### `proportions_figure(adata, *, method: str | None=None)`

Plot mean proportions per reference cell type.

:param adata: AnnData returned by deconvolve; reads the stored proportion matrix.
:param method: None infers a sole method; specify it for multiple results.
:returns: A matplotlib Figure without writing files.
:raises ValueError: No unique stored method is available.

<!-- api:end -->

## Methods and parameters

FlashDeconv, cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight and CARD
remain available. Python method options omit CLI prefixes; see
[parameters](references/parameters.md) and [matrix conventions](references/methodology.md).
The default cell2location budget is 30,000 epochs; select a method explicitly
for a quick exploratory run.

## Gotchas

- `deconvolve` requires a labelled reference AnnData for every backend.
- `deconvolve` validates finite nonnegative expression and integer counts for count models.
- `proportions` needs a method when more than one result is stored; missing cell-type metadata raises an error.
- `run_info` reports method parameters and seed. RCTD, SPOTlight and CARD retain unseeded R wrappers, so results vary between runs.
- `--demo` exits with a reference-data requirement; use the executable synthetic step for demonstration.

## Inputs and outputs

Functions return AnnData, DataFrames and Figures. CLI output includes
processed.h5ad, tables/proportions.csv, reports and conditional gallery files.
See the complete [output contract](references/output_contract.md).

## CLI

```bash
python skills/spatial/spatial-deconv/spatial_deconv.py --input spatial.h5ad --reference reference.h5ad --method flashdeconv --output results/deconv
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`anndata`, `cell2location`, `flashdeconv`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `scvi-tools`, `seaborn`, `tangram-sc`, `torch`

R backends need Rscript and spacexr (RCTD), SPOTlight or CARD.
