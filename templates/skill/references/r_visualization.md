# R Enhanced Visualization

<!--
OPTIONAL.  Only fill in if this skill emits `figure_data/*.json` payloads
that an R post-renderer can consume to produce publication-quality figures.

Three-tier visualization flow (CLAUDE.md routing reference):
  1. First run: Python standard figures (matplotlib / seaborn).
  2. R Enhanced: `omicsclaw.py replot <skill> --output dir/` re-renders
     ggplot2 figures from existing `figure_data/`.
  3. Parameter tuning: `replot <skill> --output dir/ --renderer X --top-n N`.

If this skill does NOT have an R post-renderer, leave this file as-is or
remove the body — the lint only requires the file to exist.
-->

This skill does not yet expose an R Enhanced renderer.  Skip this file
until a renderer is added under `r_visualization/<name>_publication_template.R`.
