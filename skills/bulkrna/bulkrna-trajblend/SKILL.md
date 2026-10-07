---
name: bulkrna-trajblend
description: Load when placing bulk RNA-seq samples on a single-cell reference's pseudotime axis (NNLS
  deconvolution + nearest-neighbour mapping). Skip when plain cell-type proportions (use bulkrna-deconvolution);
  native single-cell trajectory inference (use sc-pseudotime).
trigger: trajblend, trajectory, bulk to single cell, interpolation, bulk2single, VAE, deconvolution trajectory
tags:
- bulkrna
- trajectory
- pseudotime
- deconvolution
- single-cell
---

# bulkrna-trajblend

## When to use

Place bulk samples on an observed single-cell pseudotime axis and estimate
cell-type fractions. Use `bulkrna-deconvolution` for fractions without placement
and `sc-pseudotime` to infer a trajectory on the reference first.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('bulkrna-trajblend')
data, reference, labels, pseudotime = library.demo_data(random_state=42)
result = library.map_trajectory(data, reference=reference, labels=labels, pseudotime=pseudotime)
write_output(result, 'tables/pseudotime_estimates.csv')
```

For real files, pass `read_fastq`, `read_log` or `read_reference` as appropriate
to `read_input(..., reader=...)`. `examples/example_step.py` is executable.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `read_reference(path: str | Path, *, cell_type_key: str='cell_type', pseudotime_key: str='pseudotime') -> tuple`

Read a reference with annotations; pass this function as reader= to read_input.

:param path: H5AD with expression in X, or cell-by-gene CSV/TSV with annotation columns.
:param cell_type_key: CLI default cell_type; change for a named annotation column.
:param pseudotime_key: CLI default pseudotime; supply an observed reference trajectory value.
:returns: Cell-by-gene DataFrame, indexed cell-type Series and indexed pseudotime Series.
:raises ValueError: Required annotations are missing.
:raises ImportError: H5AD reading needs anndata; install it with install_skill_deps.

### `map_trajectory(bulk: pd.DataFrame, *, reference: pd.DataFrame, labels: pd.Series, pseudotime: pd.Series, k: int=15, random_state: int=42) -> pd.DataFrame`

Return bulk pseudotime estimates from NNLS and joint PCA/kNN placement.

:param bulk: Sample-by-gene nonnegative expression on a scale comparable with the reference.
:param reference: Cell-by-gene expression with at least fifty shared genes.
:param labels: Cell-type labels indexed by reference cell identifiers.
:param pseudotime: Observed reference pseudotime indexed by cell identifiers; never synthesized.
:param k: CLI default 15 nearest reference cells; reduce for a smaller reference.
:param random_state: CLI seed 42 forwarded to PCA; change to assess randomized-solver sensitivity.
:returns: New sample-indexed pseudotime table; fractions and embeddings remain in attrs.
:raises ValueError: Matrices, annotations, gene overlap or neighbor count are invalid.
:raises ImportError: Missing scipy/scikit-learn; use install_skill_deps.

### `fractions(result: pd.DataFrame) -> pd.DataFrame`

Return the estimated cell-type fractions.

:param result: Output of map_trajectory retaining attrs.
:returns: A separate sample-by-cell-type DataFrame.
:raises KeyError: Fraction diagnostics are absent.

### `run_info(result: pd.DataFrame, *, keep: bool=True) -> dict`

Read placement diagnostics and plot data.

:param result: Output of map_trajectory.
:param keep: True preserves attrs; False removes diagnostics before serialization.
:returns: Separate method, seed, fractions, embedding and annotation values.
:raises TypeError: The result is not a DataFrame.

### `trajectory_figure(result: pd.DataFrame)`

Plot bulk and reference PCA coordinates colored by reference pseudotime.

:param result: Placement result retaining its diagnostic attrs.
:returns: A matplotlib Figure without writing files.
:raises KeyError: Embedding diagnostics are absent.

### `fractions_figure(result: pd.DataFrame)`

Plot sample-by-cell-type proportions.

:param result: Placement result retaining its diagnostic attrs.
:returns: A matplotlib Figure without writing files.
:raises KeyError: Fraction diagnostics are absent.

### `demo_data(*, random_state: int=42) -> tuple`

Generate synthetic bulk mixtures and an annotated reference in memory.

:param random_state: CLI seed 42; change for another simulation without global RNG mutation.
:returns: Bulk table, reference table, cell-type Series and pseudotime Series.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

`map_trajectory` takes sample/cell rows and gene columns. NNLS estimates cell-type
fractions. Joint reference-plus-bulk log1p expression is standardized, projected
with PCA, and mapped with 15 nearest reference cells. Use comparable expression
scales; at least 50 shared genes are required. PCA receives `random_state=42`.
The CLI's `--n-epochs` remains unused; no VAE or GNN is fitted.

## Gotchas

- `read_reference` requires cell_type and pseudotime annotations; it does not fabricate Unknown labels or zero pseudotime.
- `map_trajectory` aligns both annotation Series by reference cell index.
- `pseudotime_std` is neighbor spread, not a calibrated confidence interval.
- `run_info` retains fractions and PCA coordinates in DataFrame attrs; CSV serialization does not preserve them.

## Inputs and outputs

The CLI writes these artifacts; functions return DataFrames and Figures without writing them:

- `tables/cell_fractions.csv`
- `tables/pseudotime_estimates.csv`
- `figures/fraction_heatmap.png`
- `figures/bulk_on_trajectory.png`
- `figures/pseudotime_distribution.png`
- `figures/trajectory_embedding.png`
- `report.md`
- `result.json`
- `reproducibility/commands.sh`

## CLI

```bash
python skills/bulkrna/bulkrna-trajblend/bulkrna_trajblend.py --demo --output /tmp/bulkrna_trajblend
```

For real files use `--input <file>`; trajectory placement also needs `--reference <file>`.

## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`

## Dependencies

`matplotlib`, `numpy`, `pandas`, `anndata`, `scikit-learn`, `scipy`
