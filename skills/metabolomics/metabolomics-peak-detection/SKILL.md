---
name: metabolomics-peak-detection
description: Load when running per-sample peak picking on a feature × intensity table via `scipy.signal.find_peaks`
  — emits per-(sample, feature) detected peaks with prominence and width. Skip when working with mz /
  RT raw scans (use metabolomics-xcms-preprocessing); only normalising / quantifying (use metabolomics-quantification).
trigger: peak detection, feature detection, XCMS, MZmine, MS-DIAL, peak picking
tags:
- metabolomics
- peak-detection
- find-peaks
- xcms
- mzmine
---

# metabolomics-peak-detection

## When to use

The user has a feature × sample intensity matrix (output of
`metabolomics-xcms-preprocessing` or any feature-level table)
and wants per-sample peaks detected via `scipy.signal.find_peaks`
with configurable prominence / height / distance. Sample columns
are auto-detected by name (`sample*` or `*intensity*`); override
with `--sample-prefix <prefix>`.

For raw LC-MS preprocessing use `metabolomics-xcms-preprocessing`.
For normalisation use `metabolomics-normalization`.

## Inputs & Outputs

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/detected_peaks.csv`
- `report.md`
- `result.json`

## Flow

1. Load CSV (`--input <feature_intensity.csv>`) or generate a demo at `output_dir/*.csv` (`peak_detect.py`).
2. Auto-detect sample columns: if `--sample-prefix` is set, use `c.startswith(prefix)` (`peak_detect.py`); else fall back to `"intensity" in c.lower() or c.lower().startswith("sample")`.
3. Per sample column, run `scipy.signal.find_peaks` with `prominence=`, `height=`, `distance=`.
4. Write `tables/detected_peaks.csv` (`peak_detect.py`) + `report.md` + `result.json`.

## Gotchas

- **Sample-column auto-detection is CASE-INSENSITIVE substring match.** `peak_detect.py` uses `"intensity" in c.lower() or c.lower().startswith("sample")`. Columns like `Intensity_1`, `sample_a`, `SAMPLE.5` all match; columns like `signal_1` or `abundance` do NOT — pre-rename or use `--sample-prefix signal`.
- **No sample columns ⇒ `ValueError`.** `peak_detect.py` raises `ValueError("...")` when neither auto-detection nor `--sample-prefix` matches any column.
- **`--input` REQUIRED unless `--demo`.** `peak_detect.py` raises `ValueError("--input required when not using --demo")`.
- **`--prominence` default 1e4 is intensity-unit-dependent.** Suitable for raw counts at 1e4-1e6 magnitude; for log-transformed data, set `--prominence 0.5` or smaller. Wrong threshold silently yields zero peaks.
- **`--distance` is in INDEX UNITS (sample order), not seconds.** `peak_detect.py` notes `default=5` — meaning at-least-5-row separation between adjacent peaks. If your features are RT-sorted, this corresponds to ~5 RT bins; if shuffled, the constraint is meaningless.
- **NaN values are silently treated as 0 by `find_peaks`.** Pre-impute or filter NaN rows if they affect detection.

## Key CLI

```bash
# Demo
python skills/metabolomics/metabolomics-peak-detection/peak_detect.py --demo --output /tmp/peak_demo

# Real intensity matrix (auto-detect sample columns)
python skills/metabolomics/metabolomics-peak-detection/peak_detect.py \
  --input feature_intensities.csv --output results/ \
  --prominence 1e5 --distance 3

# Custom sample-column prefix
python skills/metabolomics/metabolomics-peak-detection/peak_detect.py \
  --input my_table.csv --output results/ --sample-prefix replicate_
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — `scipy.signal.find_peaks` semantics, prominence vs height
- `references/output_contract.md` — `tables/detected_peaks.csv` schema
- Adjacent skills: `metabolomics-xcms-preprocessing` (upstream — converts raw LC-MS to feature × sample matrix), `metabolomics-quantification` (parallel — impute + normalise), `metabolomics-annotation` (downstream — annotate features against databases), `metabolomics-normalization` (downstream — log / median / quantile)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`, `scipy`
