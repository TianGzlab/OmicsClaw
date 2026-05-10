## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── detected_peaks.csv
```

## File contents

- `tables/detected_peaks.csv` — per-(sample, feature) peak with columns `sample`, `feature_id`, `prominence`, `width`. Written at `peak_detect.py:306`.
- `report.md` — Markdown summary with detection parameters and per-sample peak counts.
- `result.json` — `summary` includes `n_samples`, `mean_prominence`, plus the `--prominence` / `--height` / `--distance` / `--sample-prefix` settings.

## Notes

- No `figures/` directory.
- Peak detection runs per sample column independently (`scipy.signal.find_peaks`).
