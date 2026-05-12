---
name: proteomics-de
description: Load when computing two-group differential protein abundance (group2 vs group1, log2FC + p-value + BH-adjusted FDR) via Welch t-test, equal-variance t-test, or Mann-Whitney on a wide protein × sample CSV. Skip when you need multi-condition DE (run pairwise contrasts manually) or label-based TMT linear-mixed models.
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- proteomics
- differential-expression
- ttest
- welch
- mann-whitney
- bh-fdr
requires:
- pandas
- numpy
- scipy
---

# proteomics-de

## When to use

The user has a wide protein × sample CSV (rows = proteins as
index, columns = samples) and wants two-group differential
abundance. Three backends:

- `ttest` (default) — Student's two-sample t-test (equal variance).
- `welch` — Welch's t-test (unequal variance).
- `mann_whitney` — non-parametric Mann-Whitney U.

All return per-protein `log2fc` (group2 vs group1), `pvalue`, and
BH-adjusted `padj`. `--alpha` controls significance threshold for
the `tables/significant.csv` shortlist; `--log2fc-threshold`
optionally adds an absolute log2FC filter.

For multi-condition DE, run pairwise contrasts manually. For
label-based TMT linear-mixed models, use MSstats / limma in R.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Protein × sample table | `.csv` with protein index in column 0 and equal-count sample columns | yes (unless `--demo`) |
| Method | `--method {ttest,welch,mann_whitney}` (default `ttest`) | no |
| Significance | `--alpha <float>` (default 0.05); `--log2fc-threshold <float>` (default 0.0) | no |

| Output | Path | Notes |
|---|---|---|
| Full results | `tables/differential_abundance.csv` | per-protein `log2fc`, `pvalue`, `padj`, `group1_mean`, `group2_mean` |
| Significant subset | `tables/significant.csv` | filtered by `--alpha` (and optional `--log2fc-threshold`) |
| Report | `report.md` + `result.json` | `summary["method"]`, `summary["n_tested"]`, `summary["n_significant"]` |

## Flow

1. Load CSV with `pd.read_csv(args.input_path, index_col=0)` (`proteomics_de.py:289`); split columns at midpoint — first half = group1, second half = group2 (`:290-292`). NO CLI flag for prefix/suffix.
2. Dispatch on `--method` (`proteomics_de.py:295`); per-protein test → `log2fc` (mean(log2(g2)) − mean(log2(g1))) + raw `pvalue`.
3. Apply BH FDR adjustment (`proteomics_de.py:137` / `:178`) → `padj` column.
4. Filter `padj < args.alpha` (and `|log2fc| ≥ args.log2fc_threshold` if > 0) → `tables/significant.csv`.
5. Write `tables/differential_abundance.csv` (`proteomics_de.py:299`) + `tables/significant.csv` (`:306`) + `report.md` + `result.json` (`:322`).

## Gotchas

- **Group assignment is by COLUMN POSITION — first half / second half.** `proteomics_de.py:290-292` splits `data.columns[:mid]` vs `data.columns[mid:]`. There is NO CLI flag for control / treatment prefixes; if your CSV columns are interleaved, pre-sort them. Demo uses `control_1..N` then `treatment_1..N` (`:204-205`).
- **Index column 0 is treated as the protein ID.** `pd.read_csv(args.input_path, index_col=0)` (`proteomics_de.py:289`) is unconditional — make sure your protein-ID column is the FIRST column in the CSV.
- **Unknown `--method` raises `ValueError`.** `proteomics_de.py:192` rejects values outside `("ttest", "welch", "mann_whitney")` — argparse `choices=` enforces this at parse time too.
- **`--input` REQUIRED unless `--demo`.** `proteomics_de.py:288` raises `ValueError("--input required")`.
- **log2FC direction: group2 minus group1.** Positive `log2fc` means group2 > group1. If your "control" is in the second half of columns, you'll get inverted signs — the script does NOT auto-detect direction.
- **NaN handling differs per backend.** `ttest` / `welch` (`proteomics_de.py:116-118`) drop rows where either group's mean is non-finite (`np.isfinite` filter). `mann_whitney` (`:150-151`) additionally drops `0` values (`g1 > 0`, `g2 > 0`) — small placeholder intensities silently disappear from Mann-Whitney runs but stay in t-test runs. Pre-impute zeros if you need consistent behaviour.

## Key CLI

```bash
# Demo
python omicsclaw.py run proteomics-de --demo --output /tmp/de_demo

# Real CSV (first half = group1, second half = group2)
python omicsclaw.py run proteomics-de \
  --input protein_abundance.csv --output results/ \
  --method welch --alpha 0.05 --log2fc-threshold 1.0

# Mann-Whitney (non-parametric)
python omicsclaw.py run proteomics-de \
  --input protein_abundance.csv --output results/ \
  --method mann_whitney --alpha 0.01
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — t-test / Welch / Mann-Whitney trade-offs, BH FDR
- `references/output_contract.md` — `tables/differential_abundance.csv` schema
- Adjacent skills: `proteomics-quantification` (upstream — produces protein abundance), `proteomics-data-import` (upstream — schema normalisation), `proteomics-enrichment` (downstream — pathway enrichment on significant proteins), `proteomics-ptm` (parallel — PTM site analysis)
