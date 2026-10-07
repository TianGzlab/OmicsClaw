---
name: metabolomics-xcms-preprocessing
description: Load when exercising the CLI and replay pipeline with a synthetic LC-MS peak table. Skip real mzML preprocessing (run XCMS externally); table peak picking belongs to metabolomics-peak-detection.
trigger: xcms demo, synthetic metabolomics peaks
tags:
- metabolomics
- demo
- cli-only
---

# metabolomics-xcms-preprocessing

## When to use

This CLI generates synthetic peak tables only. It does not read mzML spectra,
run XCMS, align retention times or perform gap filling. Real `--input` runs
fail before writing results. Use XCMS externally for raw LC-MS analysis.
The skill remains CLI-only because it has no implemented scientific analysis
that can be exposed as a computational function library.

## Inputs & Outputs

`--demo` needs no input. Outputs are `tables/peak_table.csv`, `report.md`,
`result.json` and `reproducibility/commands.sh`. The table contains synthetic
m/z bounds, retention-time bounds, integrated/maximum intensities and five
sample columns. There are no Figures or AnnData outputs.

## Flow

1. Reject real input and invalid ppm/peak-width settings.
2. Generate a seeded synthetic peak table using the supplied demo parameters.
3. Write the CSV, report, result envelope and command record.

## Gotchas

- `xcms_preprocess_python` uses seed 42 and never reads spectra. The name is historical.
- `--demo --ppm 5` changes `tables/peak_table.csv` from 1,200 to 240 rows with default peak widths; these are simulated parameter responses.
- `result.json` summary contains n_samples, n_peaks, mz_min, mz_max, rt_min and rt_max. They describe the simulation only.

## Key CLI

```bash
python skills/metabolomics/metabolomics-xcms-preprocessing/metabolomics_xcms_preprocessing.py --demo --output /tmp/xcms_demo
```

Steps call `run_cli('metabolomics-xcms-preprocessing', '--demo')`.
[examples/example_step.py](examples/example_step.py) records and checks the
synthetic peak table through the step runner and fresh replay.

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)
- metabolomics-peak-detection and metabolomics-quantification accept feature tables.

## Dependencies

`numpy`, `pandas`
