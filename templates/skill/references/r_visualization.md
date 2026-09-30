# R Enhanced Visualization

<!--
OPTIONAL.  Only fill in if this skill emits `figure_data/*.json` payloads
that an R post-renderer can consume to produce publication-quality figures.

Three-tier visualization flow (CLAUDE.md routing reference):
  1. First run: Python standard figures (matplotlib / seaborn).
  2. R Enhanced: a renderer under `r_visualization/` consumes the
     `figure_data/` payloads the script wrote and emits ggplot2 figures.
  3. Parameter tuning: re-render with different renderer options.

Tiers 2 and 3 used to be reachable as `omicsclaw.py replot`, which lived in
the retired CLI and no longer exists. The renderers and their `figure_data/`
payloads are still produced, so today the only way to refresh a figure is to
re-run the skill or invoke the R script directly. Do not document `replot`
as available.

If this skill does NOT have an R post-renderer, leave this file as-is or
remove the body.
-->

This skill does not yet expose an R Enhanced renderer.  Skip this file
until a renderer is added under `r_visualization/<name>_publication_template.R`.
