---
name: sc-in-silico-perturbation
description: Load when predicting in-silico gene knockout effects on a normalised scRNA AnnData via GRN-based
  propagation (Python) or scTenifoldKnk (R). Skip when you have a real Perturb-seq / CRISPR screen (use
  sc-perturb); predicting drug sensitivity (use sc-drug-response).
tags:
- singlecell
- scrna
- in-silico-perturbation
- knockout
- grn
- sctenifoldknk
---

# sc-in-silico-perturbation

## When to use

The user has an unperturbed scRNA AnnData (no real CRISPR screen) and
wants to predict which genes / pathways would be affected if a target
gene were knocked out. Two methods:

- `grn_ko` (default) — Python-native: builds a correlation-based GRN
  on top variable genes, propagates the KO signal, ranks differential
  regulation. No R required.
- `sctenifoldknk` — R-backed scTenifoldKnk pipeline (manifold alignment
  KO). Requires `Rscript` + the `scTenifoldKnk` R package.

For **real** Perturb-seq / CRISPR screen data use `sc-perturb` (Mixscape
classification) and upstream `sc-perturb-prep`. For drug-target /
sensitivity prediction use `sc-drug-response`.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`

**Outputs**

- `tables/cell_metadata.csv`
- `tables/de_top_markers.csv`
- `tables/diff_regulation.csv`
- `tables/matrix.csv`
- `tables/tenifold_diff_regulation.csv`
- `figures/pvalue_distribution.png`
- `figures/r_isp_volcano.png`
- `figures/top_perturbed_genes.png`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `var`: `perturbation_dr_score`, `perturbation_p_adj`, `perturbation_FC`

## Flow

1. Load AnnData (`--input`) or generate demo data with `G10` as the default KO gene.
2. Preflight `--ko-gene` is in `var_names` (`SystemExit(1)` with sample-genes hint if not).
3. Warn if `layers["counts"]` is missing (uses `.X` for GRN), if `n_obs < 50`, or `n_vars < 20`.
4. For `sctenifoldknk`: check `Rscript` is on PATH; SystemExit(1) with install hint if not.
5. Detect species hint (UPPER → human, Title → mouse) from `var_names` casing.
6. Run the chosen backend; for Python `grn_ko` build the correlation GRN at `--corr-threshold` and propagate the KO.
7. Detect degenerate output (no significant regulation) → record diagnostics; do NOT raise.
8. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **All preflight failures `raise SystemExit(1)`, not `ValueError`.** `sc_in_silico_perturbation.py` raises `SystemExit(1)` when `--ko-gene` is not in `var_names` (after printing a multi-option fix message including the first 5 sample genes); raises `SystemExit(1)` when `sctenifoldknk` is selected but `Rscript` isn't on PATH; raises `SystemExit("Provide --input or use --demo")` when neither is given. Wrappers expecting `ValueError` need to catch `SystemExit`.
- **`grn_ko` is forgiving on data quality — only warnings.** When `layers["counts"]` is absent / `n_obs < 50` / `n_vars < 20`, the script logs warnings and continues (`sc_in_silico_perturbation.py`). The GRN built from `.X` (instead of raw counts) is still scored, but the result is a "best-effort" — check `result.json["preflight_warnings"]` before quoting it.
- **`--ko-gene` default is `G10`.** `sc_in_silico_perturbation.py` defaults to a synthetic gene name. On real data without specifying `--ko-gene`, the preflight will reject the run unless the data happens to contain `G10`.
- **Degenerate output is a soft fail.** When the GRN finds no significantly regulated genes, `sc_in_silico_perturbation.py` records `diagnostics["n_significant"] = 0` and the report's degenerate-block fix-suggestion list is written by `_write_report` — but the script returns 0. Always check `result.json["n_significant"]` before consuming the regulated-gene table.
- **`sctenifoldknk` does its own validation.** Once `Rscript` is found, the R-side script runs and may fail with R-specific errors not captured by the Python preflight. Check the stderr of the run and `tables/tenifold_diff_regulation.csv` existence after.
- **`--input` mandatory unless `--demo`.** `sc_in_silico_perturbation.py` raises `SystemExit("Provide --input or use --demo")`.

## Key CLI

```bash
# Demo (synthetic GRN with G10 as KO target)
python skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py --demo --output /tmp/sc_iko_demo

# Default GRN-based KO on real data (must specify --ko-gene)
python skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py \
  --input clustered.h5ad --output results/ --ko-gene EGFR

# Tighter GRN (more stringent correlation threshold)
python skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py \
  --input clustered.h5ad --output results/ \
  --ko-gene EGFR --corr-threshold 0.1 --n-top-genes 3000

# scTenifoldKnk (R-backed)
python skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py \
  --input clustered.h5ad --output results/ \
  --method sctenifoldknk --ko-gene EGFR --n-cores 4
```

## See also

- `references/parameters.md` — every CLI flag, GRN tunables
- `references/methodology.md` — `grn_ko` correlation-GRN math vs scTenifoldKnk manifold alignment
- `references/output_contract.md` — `tables/diff_regulation.csv` column schema
- Adjacent skills: `sc-perturb` / `sc-perturb-prep` (parallel — REAL Perturb-seq data, NOT in-silico), `sc-drug-response` (parallel — drug-target sensitivity prediction, NOT genetic KO), `sc-grn` (parallel — explicit GRN construction; this skill builds one internally for `grn_ko`), `sc-clustering` / `sc-cell-annotation` (upstream — produces the labelled AnnData; KO predictions are more interpretable per-cluster)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `statsmodels`
