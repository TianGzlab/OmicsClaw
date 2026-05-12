---
name: metabolomics-xcms-preprocessing
description: Load when running an XCMS-style preprocessing summary on LC-MS metabolomics raw / vendor-converted files — emits a peak table with m/z, retention time, and per-sample intensities. Skip when working with an already-built peak table (use `metabolomics-peak-detection`) or when only annotation is needed (use `metabolomics-annotation`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- metabolomics
- xcms
- preprocessing
- peak-detection
- lc-ms
- gc-ms
- centwave
requires:
- pandas
- numpy
---

# metabolomics-xcms-preprocessing

## When to use

The user has LC-MS / GC-MS metabolomics files (or a placeholder
multi-file list) and wants the standard XCMS-style preprocessing
output: peak table with `mz`, `rt`, and per-sample intensity
columns. The skill mirrors the canonical CentWave + Obiwarp +
correspondence + gap-fill workflow conceptually but is pure
Python — there is no rcpp / xcms R bridge here.

For per-sample peak picking from a single intensity matrix use
`metabolomics-peak-detection`. For metabolite annotation use
`metabolomics-annotation`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Raw / converted MS files | `--input <file1> [<file2> ...]` (multi-file via `nargs="+"`) | yes (unless `--demo`) |
| ppm | `--ppm <float>` (default 25.0) — m/z tolerance | no |
| Peak width | `--peakwidth-min` / `--peakwidth-max` (default 10.0 / 60.0 sec) | no |

| Output | Path | Notes |
|---|---|---|
| Peak table | `tables/peak_table.csv` | features × (mz, rt, intensities…) — long form |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load files (`--input <files>`) or generate a demo peak table (`--demo`).
2. Apply CentWave-style peak detection at the configured `--ppm` and `--peakwidth-*` parameters.
3. Write `tables/peak_table.csv` (`metabolomics_xcms_preprocessing.py:211`) + `report.md` + `result.json`.

## Gotchas

- **Pure Python — NO real XCMS / CAMERA invocation.** The script does not call R / `rcpp` / `xcms` / `CAMERA`. Demo and real-input runs both produce a synthetic-shaped peak table; for production XCMS workflows, run XCMS in R upstream and feed the resulting peak table into `metabolomics-peak-detection` or `metabolomics-quantification`.
- **`--input` accepts MULTIPLE files via `nargs="+"`.** `metabolomics_xcms_preprocessing.py:186` declares `nargs="+"`, so passing several files is the supported single-call shape. Demo ignores `--input`.
- **`--input` REQUIRED unless `--demo`.** `metabolomics_xcms_preprocessing.py:203` raises `ValueError("--input required when not using --demo")`.
- **Peak-width units are SECONDS (chromatographic).** `--peakwidth-min 10.0 --peakwidth-max 60.0` defaults assume LC-MS scan timing. For UPLC narrow peaks consider `--peakwidth-min 5 --peakwidth-max 20`.
- **`--ppm 25.0` default is broad.** Suitable for low-resolution Orbitrap / Q-TOF; for high-resolution FTMS use `--ppm 5.0`. Wrong value silently yields false positive merges.

## Key CLI

```bash
# Demo (synthetic peak table)
python omicsclaw.py run metabolomics-xcms-preprocessing --demo --output /tmp/xcms_demo

# Real LC-MS files
python omicsclaw.py run metabolomics-xcms-preprocessing \
  --input sample1.mzML sample2.mzML sample3.mzML --output results/ \
  --ppm 5.0 --peakwidth-min 5 --peakwidth-max 30
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — CentWave / Obiwarp conventions, ppm + peakwidth tuning
- `references/output_contract.md` — `tables/peak_table.csv` schema
- Adjacent skills: `metabolomics-peak-detection` (downstream — per-sample peak picking on a feature × intensity matrix), `metabolomics-annotation` (downstream — annotate features against HMDB / KEGG), `metabolomics-quantification` (downstream — impute + normalise), `metabolomics-normalization` (downstream — normalisation methods)
