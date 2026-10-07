# Output contract

The API returns AnnData, tables or a Figure without writing files. The CLI
writes the files below; it does not create alignments or FastQC reports.

- `processed.h5ad` and `standardized_input.h5ad`: merged cells, aligned
  features, sample labels, `layers["counts"]` and a count snapshot in `.raw`.
- `tables/barcode_metrics.csv`: cell barcode, sample label, total counts
  and detected genes, sorted by total counts.
- `tables/per_sample_summary.csv`: per-sample cell count and count/gene summaries.
- `figures/barcode_rank.png`, `count_complexity_scatter.png`,
  `count_distributions.png` and `sample_composition.png`.
- `figures/manifest.json`, `figure_data/manifest.json` and copies of the
  two tables under `figure_data/`.
- `report.md`, `result.json`, `reproducibility/commands.sh` and
  `reproducibility/requirements.txt`.

Existing sample labels are preserved even when explicit IDs supply new
barcode prefixes. An outer join fills missing features with zero. The
contract calls the matrix counts without validating integer values:
normalized inputs are not suitable. The demo joins two PBMC3k halves,
not independent biological replicates.
