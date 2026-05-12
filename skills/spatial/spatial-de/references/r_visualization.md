# R Visualisation Layer

The skill ships an optional R-side publication layer in
`r_visualization/` that consumes `figure_data/` exported by the Python
run.  R scripts focus on styling and panel composition; they do **not**
recompute Scanpy ranking or PyDESeq2 inference.

See `r_visualization/README.md` for the full input contract and template
list.  The current entrypoint is
`r_visualization/de_publication_template.R`.

## Input contract

After `oc run spatial-de ...` finishes, the output directory contains:

- `figure_data/de_plot_points.csv` — per-gene volcano coordinates
- `figure_data/top_de_hits.csv` — top markers per group
- `figure_data/group_de_metrics.csv` — group-level burden summary

The R templates read these CSVs verbatim — no AnnData round-trip.
