---
name: metabolomics-normalization
description: Load when normalising a feature × sample metabolomics CSV via median, quantile, total (sum), PQN (probabilistic quotient), or log methods — emits a normalised wide-form table. Skip when also imputing (use `metabolomics-quantification`) or for raw spectra (run `metabolomics-xcms-preprocessing` first).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- metabolomics
- normalization
- pqn
- quantile
- median
- log
requires:
- pandas
- numpy
---

# metabolomics-normalization

## When to use

The user has a feature × sample metabolomics intensity table and
wants normalisation only (no imputation). Five methods:

- `median` (default) — divide each sample by its median.
- `quantile` — quantile normalisation across samples.
- `total` — divide by per-sample total (TIC).
- `pqn` — Probabilistic Quotient Normalisation (Dieterle 2006).
- `log` — log2(x+1) per-cell.

For combined imputation + normalisation use `metabolomics-quantification`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Feature × intensity table | `.csv` (wide form: rows = features, columns = samples) | yes (unless `--demo`) |
| Method | `--method {median,quantile,total,pqn,log}` (default `median`) | no |

| Output | Path | Notes |
|---|---|---|
| Normalised table | `tables/normalized.csv` | wide form, same shape as input |
| Report | `report.md` + `result.json` | `n_features`, `n_samples`, `method` |

## Flow

1. Load CSV (`--input <features.csv>`) or generate a demo (`--demo`).
2. Dispatch on `--method`; reject unknown via `ValueError("Unknown method: {method}. Choose from {SUPPORTED_METHODS}")` at `metabolomics_normalization.py:151`.
3. Apply the chosen normalisation; write `tables/normalized.csv` (`metabolomics_normalization.py:258`) + `report.md` + `result.json`.

## Gotchas

- **`--method` choices are exact: `median` / `quantile` / `total` / `pqn` / `log`.** `metabolomics_normalization.py:36` defines `SUPPORTED_METHODS`. Aliases like `tic` (= `total`) are NOT accepted — pass `total` explicitly. (Note: sibling `metabolomics-quantification` accepts `tic` as a normalize choice; the two skills' vocabularies differ.)
- **`--input` REQUIRED unless `--demo`.** `metabolomics_normalization.py:248` raises `ValueError("--input required when not using --demo")`.
- **`pqn` requires non-zero reference values.** Probabilistic Quotient Normalisation divides by per-feature reference (median sample); features with all zeros yield NaN quotients. Pre-filter zero-prevalent features.
- **`log` is `log2(x+1)`.** Negative values raise / propagate NaN. Pre-clip upstream.
- **No imputation is performed.** NaN values pass through normalisation untouched (most methods skipna; `quantile` may NaN-propagate). Pre-impute with `metabolomics-quantification` if NaNs are problematic.
- **Method-specific behaviour with NaN may differ.** `median` / `total` use `np.nanmedian` / `np.nansum`; `quantile` may collapse rows with NaN; `pqn` expects all-numeric.

## Key CLI

```bash
# Demo (median normalize)
python omicsclaw.py run metabolomics-normalization --demo --output /tmp/norm_demo

# PQN
python omicsclaw.py run metabolomics-normalization \
  --input features.csv --output results/ --method pqn

# Total (TIC)
python omicsclaw.py run metabolomics-normalization \
  --input features.csv --output results/ --method total

# log2(x+1)
python omicsclaw.py run metabolomics-normalization \
  --input features.csv --output results/ --method log
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — per-method semantics, when each wins
- `references/output_contract.md` — `tables/normalized.csv` schema
- Adjacent skills: `metabolomics-quantification` (parallel — combined impute + normalise), `metabolomics-xcms-preprocessing` (upstream), `metabolomics-peak-detection` (upstream), `metabolomics-statistics` (downstream — multi-group testing), `metabolomics-de` (downstream — two-group DE)
