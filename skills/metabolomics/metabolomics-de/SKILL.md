---
name: metabolomics-de
description: Load when running two-group metabolomics DE (t-test + log2FC + BH-FDR + PCA) on a feature × sample CSV using `--group-a-prefix` / `--group-b-prefix` (default `ctrl` / `treat`). Skip when needing tunable test backends (use `metabolomics-statistics` for Wilcoxon / ANOVA / Kruskal) or for raw spectra.
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- metabolomics
- de
- ttest
- pca
- bh-fdr
- biomarker
requires:
- pandas
- numpy
- scipy
- scikit-learn
---

# metabolomics-de

## When to use

The user has a feature × sample metabolomics CSV with column-name
prefixes encoding the two-group design (default `ctrl` for control,
`treat` for treatment) and wants univariate t-test + log2FC +
BH-FDR + a PCA scatter as the canonical "two-group differential
analysis" output.

`--group-a-prefix` and `--group-b-prefix` are user-tunable
(defaults `ctrl` and `treat`). For more test backends
(Wilcoxon / ANOVA / Kruskal) use `metabolomics-statistics`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Feature × sample table | `.csv` with sample columns starting `ctrl*` and `treat*` (or matching the user-supplied prefixes) | yes (unless `--demo`) |
| Group prefixes | `--group-a-prefix <str>` (default `ctrl`), `--group-b-prefix <str>` (default `treat`) | no |

| Output | Path | Notes |
|---|---|---|
| Full DE results | `tables/differential_features.csv` | per-feature `pvalue`, `fdr` (BH), `log2fc`, group means |
| Significant subset | `tables/significant_features.csv` | filtered by hard-coded `fdr < 0.05` |
| PCA scatter (when ≥ 3 samples per group) | `figures/pca_scores.png` | best-effort, may be skipped on tiny inputs |
| Report | `report.md` + `result.json` | `n_features`, `n_significant` |

## Flow

1. Load CSV (`--input <features.csv>`) or generate a demo at `output_dir/<demo>.csv` (`met_diff.py:279`).
2. Filter group columns by prefix (`met_diff.py:287-288`); raise `ValueError("Could not find columns starting with '...' / '...'")` at `:291` if either group is empty.
3. Run univariate t-test → `pvalue` + BH-adjusted `fdr` + log2FC (`met_diff.py:run_univariate`).
4. Filter `fdr < 0.05` (HARD-CODED, `met_diff.py:303-304`) → `tables/significant_features.csv`.
5. Best-effort PCA on `group_a_cols + group_b_cols` → `figures/pca_scores.png`; failures are logged not raised.
6. Write `tables/differential_features.csv` (`met_diff.py:301`) + `tables/significant_features.csv` (`:305`) + report + result.json.

## Gotchas

- **Default prefixes are `ctrl` and `treat`.** `met_diff.py:271-272` defaults `--group-a-prefix=ctrl` and `--group-b-prefix=treat`. Real input column names like `Control_1` / `Treated_1` (capital, different word) need explicit `--group-a-prefix Control_ --group-b-prefix Treated_`.
- **Empty group ⇒ `ValueError`.** `met_diff.py:291-294` raises `ValueError("Could not find columns starting with '...' / '...'")` when either filter returns no columns. Sanity-check the prefixes.
- **FDR threshold is HARD-CODED at 0.05.** `met_diff.py:303-304` filters `de_result[de_result["fdr"] < 0.05]` — there is NO `--alpha` flag. Use `metabolomics-statistics` if you need a tunable significance threshold.
- **`--input` REQUIRED unless `--demo`.** `met_diff.py:282` raises `ValueError("--input required when not using --demo")`.
- **PCA is best-effort.** `met_diff.py:309-310` wraps `run_pca` in `try / except` — failures (e.g. < 3 samples per group, all-NaN features) only log a warning. The DE table is still written.
- **Test backend is fixed at t-test (Welch).** No `--method` flag here — for backend choice use sibling `metabolomics-statistics`.

## Key CLI

```bash
# Demo
python omicsclaw.py run metabolomics-de --demo --output /tmp/de_demo

# Real CSV with default ctrl_/treat_ prefixes
python omicsclaw.py run metabolomics-de \
  --input quantified_features.csv --output results/

# Custom prefixes
python omicsclaw.py run metabolomics-de \
  --input my_features.csv --output results/ \
  --group-a-prefix Control_ --group-b-prefix Treated_
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — t-test + log2FC + BH FDR conventions, PCA caveats
- `references/output_contract.md` — `tables/differential_features.csv` schema
- Adjacent skills: `metabolomics-statistics` (parallel — tunable backends + `--alpha`), `metabolomics-quantification` (upstream — impute + normalise), `metabolomics-normalization` (upstream — normalise only), `metabolomics-pathway-enrichment` (downstream — pathway analysis on significant features)
