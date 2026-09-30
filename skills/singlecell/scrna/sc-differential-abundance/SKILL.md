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

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/cell_meta.csv`
- `tables/cell_metadata.csv`
- `tables/condition_mean_proportions.csv`
- `tables/milo_nhood_results.csv`
- `tables/proportion_test_results.csv`
- `tables/sample_by_celltype_counts.csv`
- `tables/sample_by_celltype_proportions.csv`
- `tables/sccoda_effects.csv`
- `tables/simple_da_results.csv`
- `figures/milo_logfc_barplot.png`
- `figures/proportion_test_r_no_results.png`
- `figures/r_cell_barplot.png`
- `figures/r_cell_density.png`
- `figures/r_embedding_discrete.png`
- `figures/r_proportion_test.png`
- `figures/sample_celltype_proportions.png`
- `figures/sccoda_log2fc_barplot.png`
- `analysis_summary.txt`
- `annotated_input.h5ad`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`)

## Flow

1. Load AnnData; validate `--method`, `--fdr`, `--n-neighbors`, `--prop`, `--n-permutations`.
2. Run preflight on `--condition-key`, `--sample-key`, `--cell-type-key` — fail fast on missing columns or under-replication.
3. Build the universal composition summary (counts / proportions / condition means) and save them.
4. Dispatch to the method-specific runner (`run_milo_da` / `run_sccoda_da` / simple proportion test / R proportion test).
5. Append method-specific summary fields to `result.json` (`n_nhoods` / `n_effect_rows` / `n_cell_types` / `n_significant`, plus `backend` for milo/sccoda).
6. Save figures, `report.md`, `result.json`.

## Gotchas

- **Preflight failure raises `SystemExit(1)`, not `ValueError`.** `sc_differential_abundance.py` prints the missing-column / under-replication problems and exits the process. Common cases: `condition` / `sample` / `cell_type` columns missing, or `<2` samples per condition for `milo` / `sccoda`. Pass the actual obs column names (`--sample-key donor`, `--cell-type-key annotation`).
- **`--input` missing without `--demo` raises `SystemExit`, not `ValueError`.** `sc_differential_abundance.py` does `raise SystemExit("Provide --input or use --demo")`. Wrappers expecting standard `ValueError` need to catch `SystemExit` here.
- **`milo` / `sccoda` need pertpy installed.** Both methods route through `run_milo_da` / `run_sccoda_da` in `skills/singlecell/_lib/differential_abundance.py`; the pertpy import is lazy and surfaces as `ImportError` at call time when pertpy is absent. `simple` and `proportion_test_r` run without pertpy.
- **`proportion_test_r` requires a working R install but no pertpy.** `sc_differential_abundance.py` raises `FileNotFoundError(f"R script not found: {r_script}")` if the bundled R helper is missing from the install — typically when the package was installed without the R extra.
- **`result.json` count keys are *additive* per method, not exclusive.** All four methods write `result.json["n_cell_types"]` (set at the universal summary initialiser, `sc_differential_abundance.py`); `milo` additionally writes `n_nhoods`, `sccoda` additionally writes `n_effect_rows`, `proportion_test_r` overwrites `n_cell_types` from its `clusters` column. Downstream tools that just need "how many things were tested" can read `n_cell_types` universally.
- **`--reference-cell-type` is `sccoda`-only.** Other methods ignore the value silently. Default `"automatic"` lets scCODA pick.

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
