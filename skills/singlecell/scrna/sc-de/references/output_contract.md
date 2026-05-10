<!-- Hand-ported from the legacy SKILL.md ## Output Contract section. -->
<!-- Future migrations recover this automatically (added "output contract" -->
<!-- to OUTPUT_HEADINGS in scripts/migrate_skill.py). -->

# Output Contract

A successful run writes:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/de_full.csv`
- `tables/markers_top.csv`
- `figure_data/manifest.json`
- `reproducibility/commands.sh`

## Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven
gallery:

**Exploratory methods** (`wilcoxon`, `t-test`, `logreg`, `mast`):

- `figures/marker_dotplot.png`
- `figures/rank_genes_groups.png`
- `figures/de_effect_summary.png`
- `figures/de_group_summary.png`

**Pseudobulk path** (`deseq2_r`):

- `figures/pseudobulk_group_summary.png`
- per-celltype `*_volcano.png`
- per-celltype `*_ma.png`

## What Users Should Inspect First

1. `report.md`
2. `tables/de_full.csv`
3. `tables/markers_top.csv`
4. `figures/de_group_summary.png` or pseudobulk summary figures
5. `processed.h5ad`

## Result JSON Keys

- `summary.expression_source` — which matrix actually drove DE: `layers.counts`,
  `adata.raw`, or `adata.X`.  Sanity-check this is correct for the chosen
  method (raw counts for `deseq2_r`; normalized for the rest).
- `summary.method`, `summary.groupby`, `summary.group1`, `summary.group2` —
  echo of the statistical question the run answered.
