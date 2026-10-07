---
name: sc-perturb
description: Load when classifying perturbed vs non-perturbed cells in a Perturb-seq / CRISPR-screen scRNA
  AnnData via the pertpy Mixscape workflow. Skip when guide labels are not yet attached to the expression
  object (use sc-perturb-prep); in-silico KO predictions on unperturbed data (use sc-in-silico-perturbation).
tags:
- singlecell
- scrna
- perturbation
- perturb-seq
- crispr
- mixscape
- pertpy
---

# sc-perturb

Classify observed Perturb-seq cells with pertpy Mixscape. Guide labels and a
non-targeting control group must already exist; otherwise use `sc-perturb-prep`.
This is not an in-silico knockout predictor.

## Key CLI

```bash
python skills/singlecell/scrna/sc-perturb/sc_perturb.py --demo --seed 0 --output /tmp/sc_perturb_demo
python skills/singlecell/scrna/sc-perturb/sc_perturb.py --input prepared.h5ad --pert-key perturbation --control NT --split-by replicate --seed 0 --output results/perturb
```

`mixscape` (`--method mixscape`) is the only method. Tune `--n-neighbors`,
`--logfc-threshold`, `--pval-cutoff` and `--perturbation-type KO|OE` explicitly.

## Workflow

Upstream: `sc-perturb-prep`, or an AnnData with verified screen labels. Validate
labels, supply/compute PCA, build perturbation signatures, then classify cells.
Both pertpy stages receive `--seed` (API `random_state`, default 0).
Downstream: `sc-de` or `sc-enrichment` after reviewing target-level calls.

## Matrix Contract

Uses normalized expression. Count-like X is saved in `layers['counts']` and
log-normalized. Existing `X_pca` is reused; otherwise PCA is computed before the
legacy normalization step. Prefer an upstream PCA on appropriate normalized
features for real screens. The API leaves its input unchanged.

## Inputs & Outputs

Input: `.h5ad` with a perturbation column, control label and optional split key.
The CLI writes `processed.h5ad`, `report.md`, `result.json`,
`reproducibility/commands.sh`, `tables/mixscape_cell_classes.csv`,
`tables/mixscape_class_counts.csv`, `tables/mixscape_global_class_counts.csv`
and `figures/mixscape_global_classes.png`. Plot data and their manifest are in
`figure_data/`; R-enhanced figures are optional.

## Gotchas

- `result.json` → `data.params.split_by` records the CLI's resolved split key. A missing CLI split column warns and disables splitting; the API instead raises unless you pass `split_by=None`.
- `tables/mixscape_global_class_counts.csv` must contain biological signal before you interpret a run. Exit 0 alone does not establish an effect; the example asserts KO detection in both known-effect groups.
- `tables/mixscape_cell_classes.csv` preserves target-specific and global classes plus `mixscape_class_p_ko` (or `_oe`). Posterior probabilities are not experimental validation.
- For pertpy 1.0.3, split-based signatures use controls within each split rather than nearest-neighbour selection. `n_neighbors` affects the `split_by=None` path.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `mixscape(adata, *, pert_key='perturbation', control='NT', split_by='replicate', n_neighbors=20, logfc_threshold=0.25, pval_cutoff=0.05, perturbation_type='KO', random_state=0)`

Return an AnnData copy with Mixscape classes and posterior probabilities.

Uses normalized expression, preserving count-like X in layers['counts']
before log-normalization. split_by=None selects nearest-neighbour controls.
Both pertpy stages receive random_state; a missing control or split column
raises ValueError. Requires pertpy (validated with 1.0.3 and sklearn 1.7.2).

### `run_info(adata, *, keep: bool=True)`

Return method, seed and output columns; keep=False removes the run record.

### `class_counts(adata)`

Return class and n_cells columns for target-specific Mixscape labels.

### `global_class_counts(adata)`

Return global_class and n_cells columns for control, KO/OE and NP cells.

### `global_class_figure(adata)`

Return a Figure of global Mixscape cell counts without saving files.

<!-- api:end -->

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `pertpy`, `scanpy`, `scipy`, `scikit-learn`, `filelock`

The Python 3.11 CPU example is verified with `pertpy==1.0.3`,
`scikit-learn==1.7.2`, `anndata==0.11.4`, `statsmodels==0.14.6` and
`filelock==4.0.12`. statsmodels 0.15 removed a private import used by this pertpy
release. It also needs filelock
at import time but omits it from dependency metadata. Its dependencies include
JAX; use the separate extended environment. blitzgsea may need pip's isolated
source build, which the production wheels-only installer does not perform.
