---
name: metabolomics-quantification
description: Load when imputing missing values (min / median / KNN) and normalising (TIC / median / log)
  a feature × sample metabolomics CSV. Skip when only normalisation is needed (use metabolomics-normalization);
  the input is raw spectra (use metabolomics-xcms-preprocessing).
trigger: metabolomics quantification, imputation, feature quantification, missing values
tags:
- metabolomics
- quantification
- imputation
- normalization
- knn
- tic
---

# metabolomics-quantification

## When to use

The user has a feature × sample metabolomics intensity table and
wants missing-value imputation followed by normalisation, in a
single pass. Imputation: `min` (1/2 of column min), `median`
(per-column median), `knn` (sklearn KNNImputer). Normalisation:
`tic` (Total Ion Current per sample), `median` (per-sample
median), `log` (log2(x+1)).

Sample columns are auto-detected by name prefix `sample` /
`intensity`. For just normalisation use `metabolomics-normalization`;
for raw LC-MS use `metabolomics-xcms-preprocessing`.

## Inputs & Outputs

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/quantified_features.csv`
- `report.md`
- `result.json`

## Flow

1. Load CSV (`--input <features.csv>`) or generate a demo (`--demo`).
2. Auto-detect sample columns via `c.startswith("sample") or c.startswith("intensity")` (`met_quantify.py`); raise `ValueError("Could not auto-detect sample columns in the input file.")` if none found.
3. Impute missing values per `--impute` (`min` / `median` / `knn`); reject unknown method with `ValueError("Unknown impute method: ...")`.
4. Normalise per `--normalize` (`tic` / `median` / `log`); reject unknown method.
5. Write `tables/quantified_features.csv` (`met_quantify.py`) + `report.md` + `result.json`.

## Gotchas

- **Sample-column auto-detection is case-SENSITIVE prefix match.** `met_quantify.py` uses `c.startswith("sample") or c.startswith("intensity")`. `Sample_1` (capital S) does NOT match — pre-rename to lowercase or use `metabolomics-peak-detection`'s `--sample-prefix` (no equivalent flag here).
- **No sample columns ⇒ `ValueError`.** `met_quantify.py` raises `ValueError("Could not auto-detect sample columns in the input file.")` after both detection passes fail.
- **`--input` REQUIRED unless `--demo`.** `met_quantify.py` raises `ValueError("--input required when not using --demo")`.
- **`knn` imputation requires sklearn.** Available by default in OmicsClaw env. Imputes using `KNNImputer(n_neighbors=5)`.
- **`log` normalisation is `log2(x+1)`.** Zero → 0 (preserves zeros); negative values raise (silently propagate NaN). Pre-clip negatives upstream.
- **Imputation runs BEFORE normalisation.** This means `min` imputation uses unnormalised column min — re-running with a different `--normalize` does NOT change imputed-cell values. To get norm-aware imputation, run `metabolomics-normalization` standalone first, then use `--impute median` here on already-normalised data.

## Key CLI

```bash
# Demo
python skills/metabolomics/metabolomics-quantification/met_quantify.py --demo --output /tmp/quant_demo

# Real intensity table (default min impute + TIC normalize)
python skills/metabolomics/metabolomics-quantification/met_quantify.py \
  --input features.csv --output results/

# KNN impute + median normalize
python skills/metabolomics/metabolomics-quantification/met_quantify.py \
  --input features.csv --output results/ \
  --impute knn --normalize median

# log2(x+1) only
python skills/metabolomics/metabolomics-quantification/met_quantify.py \
  --input features.csv --output results/ \
  --impute median --normalize log
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — imputation / normalisation method semantics
- `references/output_contract.md` — `tables/quantified_features.csv` schema
- Adjacent skills: `metabolomics-xcms-preprocessing` (upstream), `metabolomics-peak-detection` (upstream), `metabolomics-normalization` (parallel — normalisation only), `metabolomics-statistics` (downstream — multi-group testing), `metabolomics-de` (downstream — two-group DE)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`, `scikit-learn`
