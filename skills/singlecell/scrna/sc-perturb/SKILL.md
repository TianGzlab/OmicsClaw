---
name: sc-perturb
description: Load when classifying perturbed vs non-perturbed cells in a Perturb-seq / CRISPR-screen scRNA AnnData via the pertpy Mixscape workflow. Skip when guide labels are not yet attached to the expression object (run sc-perturb-prep first) or for in-silico KO predictions on unperturbed data (use sc-in-silico-perturbation).
version: 0.2.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- perturbation
- perturb-seq
- crispr
- mixscape
- pertpy
requires:
- anndata
- scanpy
- numpy
- pandas
---

# sc-perturb

## When to use

The user has a scRNA AnnData from a CRISPR perturbation screen
(Perturb-seq style) where each cell already carries a perturbation
label in `obs[--pert-key]` plus a control category. The skill runs
pertpy's Mixscape workflow to:

1. Compute a per-cell perturbation signature (subtracts the matched
   control profile in `obsm["X_pca"]`).
2. Classify cells as `KO` / `NT` / `NP` (non-perturbed / escapers).
3. Report responder vs non-responder structure per perturbation +
   `--split-by` group.

Single backend: `mixscape` (forward-compatible CLI choice). For
attaching guide labels to expression first, use `sc-perturb-prep`. For
predicting perturbation effects on **unperturbed** data, use
`sc-in-silico-perturbation`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Perturb-seq AnnData | `.h5ad` with `obs[--pert-key]` containing perturbation labels + `--control` value | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | adds Mixscape `obs["mixscape_class"]` / `obs["mixscape_class_global"]` / `obs["mixscape_class_p_<lower(perturbation_type)>"]` (one column per perturbation **type**, e.g. `mixscape_class_p_ko` for `--perturbation-type KO`) |
| Per-perturbation × class | `tables/mixscape_class_counts.csv` | always |
| Global class totals | `tables/mixscape_global_class_counts.csv` | always |
| Per-cell class | `tables/mixscape_cell_classes.csv` | always |
| Figure | `figures/mixscape_global_classes.png` | always |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or generate demo Perturb-seq data.
2. Validate `obs[--pert-key]` exists and `--control` is a real category in that column.
3. Warn-and-disable `--split-by` if the column is absent (does NOT raise).
4. Compute `obsm["X_pca"]` if missing (auto-runs `sc.pp.pca`).
5. Run `pertpy.tools.Mixscape` (perturbation signature + KO/NT/NP classification).
6. Detect degenerate output (e.g., everything classified as `NP`) and write troubleshooting hints.
7. Save `processed.h5ad`, tables, figure, `report.md`, `result.json`.

## Gotchas

- **All preflight failures `raise SystemExit`, not `ValueError`.** `sc_perturb.py:228` raises `SystemExit("Provide --input or use --demo")`; `:235` raises `SystemExit("Perturbation column '<key>' not found in adata.obs. ...")` with multi-option fix hints; `:246` raises `SystemExit("Control label '<label>' not found in adata.obs['<key>']. Available labels: <list>")`. Wrappers expecting standard `ValueError` need to catch `SystemExit` here.
- **`--split-by` missing is a soft warning, not a fail.** When `--split-by` (default `replicate`) doesn't exist in `obs`, `sc_perturb.py:255-261` logs a warning and silently disables the split. The Mixscape run continues without replicate awareness — `result.json["params"]["split_by"]` will reflect the disablement.
- **PCA is computed automatically when missing.** `sc_perturb.py:264-266` calls `sc.pp.pca(adata)` if `obsm["X_pca"]` is absent — no upstream `sc-preprocessing` strictly required, but the implicit PCA uses defaults (no batch correction, no HVG). For real screens prefer running `sc-preprocessing` first so the PCA reflects HVG-selected normalised data.
- **Degenerate output (everything `NP`) is a soft fail.** `sc_perturb.py:85` defines `_detect_degenerate_output` which records diagnostics and writes troubleshooting hints to `report.md` (see `sc_perturb.py:141`+); the script does NOT raise. Always inspect `result.json["n_classes"]` (`:382`) — if it's 1, Mixscape didn't separate populations and the run is uninformative.
- **`--method mixscape` is the only choice.** `sc_perturb.py:72` argparse `choices=["mixscape"]`. `--method` exists for forward-compatibility; today any other value is rejected by argparse before the script runs.

## Key CLI

```bash
# Demo (synthetic Perturb-seq)
python omicsclaw.py run sc-perturb --demo --output /tmp/sc_perturb_demo

# Default: input has standard column names (perturbation / NT)
python omicsclaw.py run sc-perturb \
  --input perturb_prep_output/processed.h5ad --output results/

# Custom column / control names
python omicsclaw.py run sc-perturb \
  --input data.h5ad --output results/ \
  --pert-key guide_target --control non-targeting --split-by donor

# Tune Mixscape DE thresholds
python omicsclaw.py run sc-perturb \
  --input data.h5ad --output results/ \
  --logfc-threshold 0.5 --pval-cutoff 0.01 --n-neighbors 30
```

## See also

- `references/parameters.md` — every CLI flag, Mixscape tunables
- `references/methodology.md` — Mixscape signature subtraction; KO/NT/NP semantics
- `references/output_contract.md` — `obs["mixscape_class"]` / `obs["mixscape_class_global"]` schema + table layouts
- Adjacent skills: `sc-perturb-prep` (upstream — attaches guide labels to the expression object), `sc-de` (downstream — DE between perturbed and control), `sc-in-silico-perturbation` (parallel — predicts perturbation effects WITHOUT a real screen), `sc-preprocessing` (upstream — produces an HVG-aware PCA preferable to the auto-PCA inside this skill)
