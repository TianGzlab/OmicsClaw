---
name: sc-differential-abundance
description: Load when testing whether cell-type / cluster proportions or neighbourhood densities differ
  between conditions in a multi-sample scRNA AnnData via Milo, scCODA, simple proportion screen, or R
  Monte-Carlo permutation. Skip when ranking marker genes (use sc-markers); per-cell DE (use sc-de).
tags:
- singlecell
- scrna
- differential-abundance
- compositional
- milo
- sccoda
- proportion-test
---

# sc-differential-abundance

## When to use

The user has a multi-sample, multi-condition scRNA AnnData and asks
*"Did the relative abundance of these cell states change between
conditions?"* — distinct from per-cell DE. Four methods:

- `milo` (default) — neighbourhood-level DA, replicate-aware (pertpy).
- `sccoda` — Bayesian compositional analysis with a reference cell
  type (pertpy).
- `simple` — exploratory proportion screen, no pertpy needed.
- `proportion_test_r` — base-R Monte-Carlo permutation; lollipop plots
  with bootstrap 95% CI.

For per-cell **expression** changes between conditions, use `sc-de`.
For ranking *what* defines a cluster, use `sc-markers`.

## Use in an analysis step

Use `load_skill` from the notebook SDK; write returned objects with
`write_output`. This runnable example is also in `examples/example_step.py`.
The CLI remains available for standalone reports and galleries.

```python
# Recover a threefold change in a synthetic cell type using independent samples.
# Reads multisample_synthetic: four control and four treated samples.
# Calls sc-differential-abundance: test_abundance, composition, proportion_figure.

from skills._sdk.notebook import load_demo, load_skill, write_output

abundance = load_skill('sc-differential-abundance')
adata = load_demo('multisample_synthetic')

table = abundance.test_abundance(adata, method='simple')
counts, proportions = abundance.composition(adata, sample_key='sample',
    condition_key='condition', celltype_key='cell_type')
write_output(table, 'tables/abundance.csv')
write_output(counts, 'tables/sample_counts.csv')
write_output(abundance.proportion_figure(proportions), 'figures/sample_proportions.png')

enriched = table.set_index('cell_type').loc['Enriched']
assert enriched['significant']
assert enriched['log2fc_group_b_over_a'] > 1
assert counts.shape == (8, 3)
```

## Inputs & Outputs

Input is an AnnData with sample, condition and cell-type columns. Each
sample must have one condition. The Python API returns composition tables
or a method-specific result DataFrame; it does not change the input.

The CLI writes `processed.h5ad`, `annotated_input.h5ad`, `report.md`,
`result.json`, and these common tables:
`sample_by_celltype_counts.csv`, `sample_by_celltype_proportions.csv`,
`condition_mean_proportions.csv`. The selected method adds
`simple_da_results.csv`, `milo_nhood_results.csv`, `sccoda_effects.csv`,
or a nonempty `proportion_test_results.csv`. Figures depend on the method
and available results. R exchange files are temporary.

## Flow

1. Load AnnData; validate `--method`, `--fdr`, `--n-neighbors`, `--prop`, `--n-permutations`.
2. Run preflight on `--condition-key`, `--sample-key`, `--cell-type-key` — fail fast on missing columns or under-replication.
3. Build the universal composition summary (counts / proportions / condition means) and save them.
4. Dispatch to the method-specific runner (`run_milo_da` / `run_sccoda_da` / simple proportion test / R proportion test).
5. Append method-specific summary fields to `result.json` (`n_nhoods` / `n_effect_rows` / `n_cell_types` / `n_significant`, plus `backend` for milo/sccoda).
6. Save figures, `report.md`, `result.json`.

## Gotchas

- `run_info(table)["executed_method"]` distinguishes pertpy Milo from the internal `milo_like` fallback. The fallback reason includes the failed import; it is not the same method as official Milo.
- The CLI demo has only two samples per condition. Its simple/Milo-like Mann-Whitney tests cannot reach p < 0.05. The step uses `multisample_synthetic`, with four samples per condition and a known enriched cell type.
- `proportion_test_r` permutes cell labels, ignoring sample identity, and uses the existing R seed 42. It requires R; failures propagate from `test_abundance` rather than being reported as empty successful output.
- `--min-count` is accepted by the CLI but has no effect. The API does not expose that unused option.
- `run_info(table)` records seeds. `random_state` controls pertpy and newly computed neighbors; standalone scCODA retains its sampler defaults and reports no effective seed.
- CLI preflight exits on missing metadata or insufficient replication. The API raises `ValueError` for missing values or a sample assigned to multiple conditions; `composition` and `condition_proportions` use sample-level denominators.

## Key CLI

```bash
# Demo (built-in synthetic 2-condition × 4-sample data)
python skills/singlecell/scrna/sc-differential-abundance/sc_differential_abundance.py --demo \
  --method milo --output /tmp/sc_da_demo

# Milo (replicate-aware neighbourhood DA)
python skills/singlecell/scrna/sc-differential-abundance/sc_differential_abundance.py \
  --input integrated.h5ad --output results/ \
  --method milo --condition-key treatment --sample-key donor

# scCODA Bayesian compositional analysis
python skills/singlecell/scrna/sc-differential-abundance/sc_differential_abundance.py \
  --input integrated.h5ad --output results/ \
  --method sccoda --reference-cell-type "B cell" \
  --condition-key treatment --sample-key donor --cell-type-key cell_type

# Lightweight proportion screen (no pertpy)
python skills/singlecell/scrna/sc-differential-abundance/sc_differential_abundance.py \
  --input integrated.h5ad --output results/ --method simple
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each method wins; pertpy install notes
- `references/output_contract.md` — `result.json` keys per method, table column schemas
- Adjacent skills: `sc-cell-annotation` / `sc-clustering` (upstream — produce the cell-type column), `sc-de` (parallel — per-cell expression DE between conditions, NOT abundance), `sc-markers` (parallel — within-sample cluster marker ranking, NOT cross-condition)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `pertpy`, `scanpy`, `sccoda`, `scipy`, `seaborn`, `statsmodels`

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `composition(adata, *, sample_key: str, celltype_key: str, condition_key: str)`

Return sample-by-cell-type counts and row-normalized proportions.

Each sample must belong to one condition. No cells or counts are changed.

### `condition_proportions(adata, *, sample_key: str, celltype_key: str, condition_key: str) -> pd.DataFrame`

Return condition means of per-sample proportions, weighting samples equally.

### `test_abundance(adata, *, method: str='milo', sample_key: str='sample', condition_key: str='condition', celltype_key: str='cell_type', contrast: str | None=None, reference_cell_type: str='automatic', fdr: float=0.05, prop: float=0.1, n_neighbors: int=30, n_permutations: int=1000, random_state: int=0) -> pd.DataFrame`

Return differential-abundance results without changing adata.

simple tests sample proportions with two-sided Mann-Whitney and BH.
milo uses pertpy, or the existing milo_like neighborhood screen when its
import fails; run_info names the executed backend and reason. scCODA uses
pertpy or the installed standalone sccoda backend. random_state controls
pertpy and newly computed neighbors; standalone sccoda retains its sampler
defaults. proportion_test_r uses the existing fixed R seed 42 and permutes
cells, ignoring sample identity; its failures propagate instead of returning
an empty success result. This function does not apply a minimum-count filter.

### `proportion_figure(proportions: pd.DataFrame)`

Return a sample-by-cell-type proportion heatmap without writing files.

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Return backend and seed diagnostics; keep=False removes the table's run record.

<!-- api:end -->
