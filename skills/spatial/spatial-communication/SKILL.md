---
name: spatial-communication
description: Load when computing ligand-receptor communication on labelled spatial AnnData with LIANA, CellPhoneDB, FastCCC or CellChat. Skip unlabelled data (use spatial-annotate) and non-spatial scRNA analysis (use sc-cell-communication).
trigger: cell communication, ligand receptor, LIANA, CellPhoneDB, FastCCC, CellChat
tags:
- spatial
- communication
- ligand-receptor
---

# Spatial communication

## When to use

Infer ligand-receptor interactions between annotated populations. LIANA is
the default; CellPhoneDB and FastCCC need a local CellPhoneDB database.
CellChat runs in an R subprocess. These methods do not constrain interactions
by spatial distance: coordinates support the CLI maps, not the inference.

## API

Use `load_skill("spatial-communication")` in an analysis step.
`examples/example_step.py` uses real PBMC expression with explicitly synthetic
coordinates. The CLI demo uses synthetic expression and is not biological evidence.

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `communicate(adata, *, method='liana', cell_type_key='leiden', species='human', random_state=None, **parameters)`

Infer ligand-receptor interactions and return the same AnnData.

LIANA uses raw when present, otherwise X. Other backends read normalized
X. Coordinates support CLI maps; these methods do not impose distance filters.

:param adata: Log-normalized expression with cell-type labels; modified in place.
:param method: CLI default liana; cellphonedb, fastccc or cellchat_r also supported.
:param cell_type_key: CLI default leiden; obs column defining populations.
:param species: CLI default human; mouse supported by LIANA and CellChat.
:param random_state: None keeps LIANA seed 1337 and CellChat seed 1; CellPhoneDB uses 0.
:param parameters: Native backend keywords in references/parameters.md.
:returns: The same AnnData with canonical ccc_results and role summaries in uns.
:raises ValueError: Method, labels, species or numeric controls are invalid.
:raises ImportError: Optional backend is missing; use install_skill_deps.
:raises FileNotFoundError: CellPhoneDB/FastCCC's local database is missing.

### `interactions(adata, *, significant_only=False)`

Return ligand-receptor scores; unmeasured p values remain missing.

:param adata: AnnData returned by communicate.
:param significant_only: Default False; True selects real p values below 0.05.
:returns: A new DataFrame with ligand, receptor, source, target, score and pvalue.
:raises ValueError: No run is recorded.

### `run_info(adata, *, keep=True)`

Read the last run's diagnostics and optional backend tables.

:param adata: AnnData returned by communicate.
:param keep: Default True; False removes transient diagnostics for CLI serialization.
:returns: Summary dictionary including tested/significant counts and extra_tables.
:raises ValueError: No communication run is recorded.

### `roles_figure(adata, *, n_top=20)`

Plot population sender and receiver scores without file writes.

:param adata: AnnData returned by communicate.
:param n_top: Default 20 populations; use fewer for a smaller figure.
:returns: A matplotlib Figure, explicitly labelled when no scores exist.
:raises ValueError: No run is recorded or n_top is not positive.

<!-- api:end -->

## Key CLI

```bash
python skills/spatial/spatial-communication/spatial_communication.py \
  --input processed.h5ad --output results/communication \
  --cell-type-key cell_type --method liana --liana-n-perms 1000
python skills/spatial/spatial-communication/spatial_communication.py \
  --demo --output /tmp/communication_demo
```

## Inputs & Outputs

Input is log-normalized AnnData with at least two populations in
`obs[cell_type_key]` (default `leiden`). LIANA reads `raw` when present;
other methods read `X`. Use gene symbols, not synthetic feature identifiers.
LIANA and CellChat support human and mouse; the other wrappers support human.

The API mutates and returns the same object, preserving observation and
feature order. It stores `uns["ccc_results"]`, method-specific results,
`communication_summary`, `communication_signaling_roles`, and diagnostics.
`interactions` returns a new DataFrame; `roles_figure` returns a Figure.
Library calls do not create report directories. Optional external tools use
temporary files that are removed after execution.

The CLI writes `processed.h5ad`, `report.md`, `result.json`, reproducibility
commands, figure-data CSVs, and conditional tables/figures.
See [output inventory](references/output_contract.md) for exact conditions.

## Gotchas

- `_api.py:communicate` rejects absent labels and populations with fewer than
  two distinct labels; it does not substitute a different annotation.
- `uns["ccc_results"]` has missing p values when the backend supplies no
  statistical test. LIANA specificity ranks are not p values.
- `tables/lr_interactions.csv` is absent when no interactions are returned;
  an empty result does not establish absence of biological communication.
- `_api.py:communicate` raises an install hint for missing backends.
  CellPhoneDB/FastCCC also require a local database; no substitute is generated.
- `rscripts/cellchat.R` needs Rscript, Matrix and CellChat, not rpy2.
- `_api.py:communicate` defaults to LIANA seed 1337, CellPhoneDB 0 and
  CellChat 1; FastCCC has no seed argument.

## References

- [Parameters](references/parameters.md): CLI-to-library keyword mapping.
- [Methodology](references/methodology.md): matrix and statistical semantics.
- [Output contract](references/output_contract.md): files and AnnData keys.

## Dependencies

`anndata`, `cellphonedb`, `fastccc`, `liana`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`, `CellChat`, `Matrix`

The R backend requires an Rscript executable.
