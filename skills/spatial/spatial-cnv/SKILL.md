---
name: spatial-cnv
description: Load when inferring copy-number variation per spot on a preprocessed spatial AnnData with
  chromosome-annotated genes via infercnvpy (default — log-ratio sliding-window) or Numbat (R, allele-aware
  clone deconvolution). Skip when `var["chromosome"]` / `var["start"]` / `var["end"]` gene-coord metadata
  is missing; no normal-reference subset can be defined.
trigger: copy number variation, CNV, inferCNV, infercnvpy, Numbat, aneuploidy, chromosomal aberration, tumor clone
tags:
- spatial
- cnv
- copy-number
- infercnvpy
- numbat
- tumor
---

# spatial-cnv

## When to use

Infer expression-based CNV with infercnvpy, or allele-aware CNV with R Numbat. Gene coordinates and an appropriate diploid reference are needed for interpretation.

## Use from a step

```python
from skills._sdk.notebook import load_skill
library = load_skill("spatial-cnv")
library.cnv(adata, reference_key='cell_type', reference_cat=['Normal'])
```

Run `examples/example_step.py` with the step runner for a synthetic, executable example.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `cnv(adata, *, method: str='infercnvpy', reference_key: str | None=None, reference_cat: list[str] | str | None=None, window_size: int=100, step: int=10, method_params: dict | None=None, random_state: int=0, allele_counts: pd.DataFrame | None=None)`

Infer CNV in place from log-normalized X or Numbat raw counts.

infercnvpy needs var chromosome/start/end. Numbat needs layers['counts'],
phased allele_counts and a diploid reference annotation. Counts and metadata
are exchanged with R inside a temporary directory.

:param adata: AnnData with expression and method-specific annotations.
:param method: infercnvpy (CLI default) or numbat.
:param reference_key: Observation column marking reference cells; None uses all cells.
:param reference_cat: Reference labels; None uses the backend's global reference.
:param window_size: Genomic smoothing window, 100 genes by default.
:param step: Sliding-window stride, 10 genes by default.
:param method_params: CLI options with underscores, such as infercnv_n_jobs=1;
    None keeps defaults listed in references/parameters.md.
:param random_state: infercnvpy PCA/graph/clustering and Numbat R seed, default 0.
:param allele_counts: Numbat long-form DataFrame with cell/snp_id/CHROM/POS/AD/DP/GT/gene;
    None reads the legacy obsm['allele_counts'] table. Multiple SNPs per cell are allowed.
:returns: The same AnnData with CNV matrices, scores and JSON diagnostics.
:raises ValueError: Missing genomic annotations, raw counts or invalid parameters.
:raises ImportError: Missing infercnvpy or R backend; use install_skill_deps.

### `run_info(adata, *, keep: bool=True) -> dict`

Read the last CNV inference diagnostics.

:param adata: AnnData returned by cnv.
:param keep: True retains diagnostics; False removes them before CLI serialization.
:returns: Method, score summary, seed and any fallback details, or an empty dict.

### `scores(adata) -> pd.DataFrame`

Return CNV scores and labels in observation order.

:param adata: AnnData after CNV inference.
:returns: Barcode-indexed table of available CNV score/label/uncertainty columns.

### `cnv_figure(adata, *, basis: str='spatial')`

Plot CNV scores over supplied coordinates without saving.

:param adata: AnnData after CNV inference.
:param basis: Coordinate key, spatial by default; X_umap is also supported.
:returns: A matplotlib Figure owned by the caller.
:raises KeyError: Missing coordinates or CNV score.

<!-- api:end -->

## Methods and parameters

infercnvpy uses log-normalized X, a 100-gene window and stride 10. Numbat uses integer layers['counts'] and phased allele counts. Pass method-specific CLI option names with underscores in `method_params`.
See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `cnv` rejects missing genomic `chromosome`, `start` and `end` columns for infercnvpy.
- `cnv` requires real counts and `obsm['allele_counts']` for Numbat; the example uses explicitly synthetic coordinates only for infercnvpy.
- `run_info` records the clustering fallback if infercnvpy cannot build Leiden groups.
- `cnv(..., allele_counts=table)` accepts multiple SNP rows per cell; its R subprocess uses the requested random seed.

## Inputs and outputs

`cnv` returns the same AnnData with method-specific scores. `scores` returns a DataFrame and `cnv_figure` a Figure. CLI output includes `processed.h5ad`, reports and conditional score, bin, clone and uncertainty tables/plots.
The full file inventory and conditions are in [output contract](references/output_contract.md).

## CLI

```bash
python skills/spatial/spatial-cnv/spatial_cnv.py --input input.h5ad --output results/
```

The CLI retains reports and the figure gallery. Function calls do not save files.

## See also

- `spatial-preprocess` supplies expression preprocessing.
- [Output contract](references/output_contract.md) lists method-specific files and AnnData fields.

## Dependencies

`anndata`, `infercnvpy`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`, `Matrix`, `numbat`
