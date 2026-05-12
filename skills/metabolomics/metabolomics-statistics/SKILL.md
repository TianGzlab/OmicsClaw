---
name: metabolomics-statistics
description: Load when running univariate two-group testing (t-test / Wilcoxon / ANOVA / Kruskal-Wallis) on a feature × sample metabolomics CSV with `--group1-prefix` / `--group2-prefix` column matching, BH-FDR adjusted. Skip when working with raw spectra (run `metabolomics-xcms-preprocessing`) or for two-group DE with default `ctrl` / `treat` prefixes (use `metabolomics-de`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- metabolomics
- statistics
- ttest
- wilcoxon
- anova
- kruskal
- bh-fdr
requires:
- pandas
- numpy
- scipy
---

# metabolomics-statistics

## When to use

The user has a wide feature × sample CSV (rows = features as
index, columns = samples) and wants univariate two-group testing.
Four backends:

- `ttest` (default) — Welch's two-sample t-test.
- `wilcoxon` — Mann-Whitney U (non-parametric).
- `anova` — one-way ANOVA (two-group case ≡ equal-variance t-test).
- `kruskal` — Kruskal-Wallis (non-parametric ANOVA).

`--group1-prefix` / `--group2-prefix` select sample columns by
prefix; without them the script splits at column-midpoint with a
warning. Significance threshold via `--alpha` (default 0.05);
BH-FDR adjusted.

For metabolomics-DE with default `ctrl` / `treat` column prefixes
use `metabolomics-de`. For raw spectra use
`metabolomics-xcms-preprocessing`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Feature × sample table | `.csv` with feature index in column 0 + sample columns | yes (unless `--demo`) |
| Method | `--method {ttest,anova,wilcoxon,kruskal}` (default `ttest`) | no |
| Significance | `--alpha <float>` (default 0.05) | no |
| Group columns | `--group1-prefix <str>` and `--group2-prefix <str>` (else midpoint split) | no |

| Output | Path | Notes |
|---|---|---|
| Full results | `tables/statistics.csv` | per-feature columns: `feature`, `group1_mean`, `group2_mean`, `fold_change`, `log2fc`, `statistic`, `pvalue`, `fdr` (BH-adjusted) |
| Significant subset | `tables/significant.csv` | filtered by `--alpha` |
| Report | `report.md` + `result.json` | `summary["method"]`, `summary["n_significant"]` |

## Flow

1. Load CSV with `pd.read_csv(args.input_path, index_col=0)` (`metabolomics_statistics.py:325`).
2. If both `--group1-prefix` and `--group2-prefix` are set, filter columns by `c.startswith(prefix)` (`metabolomics_statistics.py:330-331`); else fall back to midpoint split with a warning (`:333-340`).
3. If either group is empty, raise `ValueError("Could not determine group columns. ...")` at `:344`.
4. Dispatch on `--method` (`:209` rejects unknown with `ValueError`); per-feature test → `pvalue` + BH-adjusted `fdr`.
5. Filter `fdr < args.alpha` → `tables/significant.csv` (`:363`).
6. Write `tables/statistics.csv` (`metabolomics_statistics.py:360`) + report + result.json.

## Gotchas

- **Group prefixes are OPTIONAL with midpoint fallback.** `metabolomics_statistics.py:329-340` only honours `--group1-prefix` / `--group2-prefix` when BOTH are passed; missing one or both falls back to midpoint split (first half / second half) with a warning. Always pass BOTH for explicit group control.
- **Empty group ⇒ `ValueError`.** `metabolomics_statistics.py:344` raises if either group's column list is empty (e.g. typo in prefix). Sanity-check `--group1-prefix` / `--group2-prefix` against your column names.
- **Index column 0 is the feature ID.** `pd.read_csv(args.input_path, index_col=0)` (`:325`) is unconditional — make sure your feature-ID column is the FIRST column in the CSV.
- **`anova` = equal-variance t-test in the two-group case** (`metabolomics_statistics.py:138-140`). For more than two groups, this skill silently assumes two — extend `group_cols` lists or use a different tool for true multi-group ANOVA.
- **`wilcoxon` here is Mann-Whitney U (independent samples), NOT paired Wilcoxon signed-rank.** Don't use it for paired designs.
- **`--input` REQUIRED unless `--demo`.** `metabolomics_statistics.py:324` raises `ValueError("--input required when not using --demo")`.
- **log2FC direction depends on group order.** `group2_mean - group1_mean` convention; pass groups in the right order.

## Key CLI

```bash
# Demo
python omicsclaw.py run metabolomics-statistics --demo --output /tmp/stats_demo

# Real CSV with explicit group prefixes
python omicsclaw.py run metabolomics-statistics \
  --input features_quant.csv --output results/ \
  --method ttest --alpha 0.05 \
  --group1-prefix control_ --group2-prefix treated_

# Wilcoxon (non-parametric)
python omicsclaw.py run metabolomics-statistics \
  --input features_quant.csv --output results/ \
  --method wilcoxon --group1-prefix WT --group2-prefix KO
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — per-method assumptions, BH FDR
- `references/output_contract.md` — `tables/statistics.csv` schema
- Adjacent skills: `metabolomics-de` (parallel — pre-set `ctrl` / `treat` prefixes), `metabolomics-quantification` (upstream — impute + normalise), `metabolomics-normalization` (upstream — normalisation only), `metabolomics-pathway-enrichment` (downstream — pathway analysis on significant features)
