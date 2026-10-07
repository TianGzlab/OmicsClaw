# Output contract

The CLI writes `processed.h5ad`, `report.md`, `result.json`,
`reproducibility/{commands.sh,requirements.txt}`, diagnostic plots under
`figures/` and reusable plot tables under `figure_data/`.
Each plot directory has a manifest. Optional R plots are written under
`figures/r_enhanced/` only when rendering succeeds.

Simple subtraction preserves the selected original counts in
`layers["counts"]`, replaces `X` with nonnegative corrected counts and
records parameters under `uns["ambient_correction"]`. SoupX records its
contamination estimate under `uns["soupx"]`. CellBender may retain its
backend files under `cellbender_output/`; the available files are listed
in `result.json["data"]["output_bundle"]`.

The CLI's `result.json["summary"]` includes `requested_method`,
`executed_method`, `fallback_used`, `fallback_reason` and count-reduction
statistics. Do not infer the executed method from the CLI argument.

The API writes no files. `correction_summary`, `counts_comparison_table`
and `ambient_profile_table` return tables; `correction_figure` returns a
Figure. Use `write_output` for each artifact. The profile helper describes
the simple mean-count profile, not SoupX's estimated ambient profile.
