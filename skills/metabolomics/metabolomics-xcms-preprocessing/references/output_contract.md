# Output contract

- `tables/peak_table.csv`: wide synthetic table with mz, mzmin, mzmax, rt,
  rtmin, rtmax, into, maxo and sample_1 through sample_5.
- `report.md`: parameters and simulation summary.
- `result.json`: summary has n_samples, n_peaks, mz_min, mz_max, rt_min and rt_max;
  data.params records ppm and peakwidth.
- `reproducibility/commands.sh`: historical command record, not a replay capsule.

No figures or H5AD files are written. Real input is rejected before outputs.
