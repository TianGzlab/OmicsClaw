---
name: proteomics-ms-qc
description: Load when computing protein-table QC — proteins × samples count, missing-value rate, intensity
  CV (median + mean) — from a MaxQuant / FragPipe / DIA-NN protein-quantification CSV. Skip when raw mzML
  / RAW spectra are the input (run a search engine first); peptide-level QC is needed (use proteomics-identification).
trigger: MS QC, mass spec QC, PTXQC, rawTools
tags:
- proteomics
- qc
- ms
- maxquant
- intensity
- missing-values
- cv
---

# proteomics-ms-qc

## When to use

The user has a protein-quantification CSV (typically the output of
`proteomics-data-import`, with rows = proteins and columns =
samples + metadata) and wants QC summary statistics: protein count,
sample count, fraction of missing intensities, per-protein
coefficient of variation (CV) — median and mean. Auto-detects
intensity columns by `select_dtypes(include=[np.number])`.

This skill does NOT process raw spectra. For peptide / PSM-level
identification stats use `proteomics-identification`.

## Inputs & Outputs

**Inputs**

- Modalities: ms
- File types: `.csv`

**Outputs**

- `tables/qc_metrics.csv`
- `report.md`
- `result.json`

## Flow

1. Load CSV (`--input <file.csv>`) or generate a demo at `output_dir/demo_proteomics.csv` (`proteomics_ms_qc.py`).
2. Detect numeric (intensity) columns via `select_dtypes(include=[np.number])` (`proteomics_ms_qc.py`); raise `ValueError("No intensity/sample columns detected in input data")` if none found.
3. Compute n_proteins / n_samples / missing_rate / per-protein CV.
4. Write `tables/qc_metrics.csv` (`proteomics_ms_qc.py`) + `report.md` + `result.json`.

## Gotchas

- **Sample columns must be NUMERIC.** Intensity-column auto-detection (`proteomics_ms_qc.py`) uses `select_dtypes(include=[np.number])`. String-typed intensities (e.g. quoted numbers in some Spectronaut exports) are silently treated as metadata, not samples — your `n_samples` will be 0 and the run raises `ValueError`.
- **No intensity columns ⇒ hard fail.** `proteomics_ms_qc.py` raises `ValueError("No intensity/sample columns detected in input data")` — there is no auto-detection of `intensity_*` prefixes; only dtype-based.
- **`--input` REQUIRED unless `--demo`.** `proteomics_ms_qc.py` raises `ValueError("--input required when not using --demo")`.
- **Both `NaN` and `0.0` count as missing.** `proteomics_ms_qc.py` computes `missing_mask = np.isnan(intensities) | (intensities == 0)` — zero is treated as "not detected" (the proteomics convention). If your search engine writes a small placeholder (e.g. `1.0`) for undetected proteins, the missing rate is artificially LOW; pre-impute placeholders to `0` or `NaN` first.
- **CV is per-protein across samples.** Reported `median_cv` / `mean_cv` are aggregations across the per-protein CV distribution — interpret as "typical protein-level reproducibility", not "sample-level reproducibility".

## Key CLI

```bash
# Demo
python skills/proteomics/proteomics-ms-qc/proteomics_ms_qc.py --demo --output /tmp/qc_demo

# Real protein table (e.g. output of proteomics-data-import)
python skills/proteomics/proteomics-ms-qc/proteomics_ms_qc.py \
  --input results/tables/proteins.csv --output qc_results/
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — CV definition, missing-value handling
- `references/output_contract.md` — `tables/qc_metrics.csv` schema
- Adjacent skills: `proteomics-data-import` (upstream — produces the protein table), `proteomics-quantification` (downstream — LFQ / iBAQ / spectral count), `proteomics-identification` (parallel — peptide-level summary), `proteomics-de` (downstream — differential abundance)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
