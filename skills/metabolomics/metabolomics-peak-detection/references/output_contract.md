# Output contract

`tables/detected_peaks.csv`, `report.md` and `result.json`. Demo mode also writes its synthetic input CSV at the output root.

The function library returns tables and Figures without file writes.
`run_info` reads DataFrame diagnostics; `keep=False` removes them.

`detect_peaks` expects mz and rt plus sample/intensity columns. `distance` and `width` are row positions, not seconds. NaNs follow scipy signal semantics and are not imputed. Empty outputs keep their CSV column schema.
