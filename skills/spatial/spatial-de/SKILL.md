---
name: spatial-de
description: >-
  Differential expression and marker discovery for spatial transcriptomics
  using Scanpy Wilcoxon / t-test or sample-aware pseudobulk PyDESeq2.
version: 0.5.0
author: OmicsClaw Team
license: MIT
tags: [spatial, differential-expression, markers, wilcoxon, t-test, pydeseq2, pseudobulk]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--fdr-threshold"
    - "--filter-compare-abs"
    - "--filter-markers"
    - "--group1"
    - "--group2"
    - "--groupby"
    - "--log2fc-threshold"
    - "--max-out-group-fraction"
    - "--method"
    - "--min-cells-per-sample"
    - "--min-counts-per-gene"
    - "--min-fold-change"
    - "--min-in-group-fraction"
    - "--n-top-genes"
    - "--no-filter-compare-abs"
    - "--no-filter-markers"
    - "--no-pydeseq2-cooks-filter"
    - "--no-pydeseq2-independent-filter"
    - "--no-pydeseq2-refit-cooks"
    - "--no-scanpy-pts"
    - "--no-scanpy-rankby-abs"
    - "--no-scanpy-tie-correct"
    - "--pydeseq2-alpha"
    - "--pydeseq2-cooks-filter"
    - "--pydeseq2-fit-type"
    - "--pydeseq2-independent-filter"
    - "--pydeseq2-n-cpus"
    - "--pydeseq2-refit-cooks"
    - "--pydeseq2-size-factors-fit-type"
    - "--sample-key"
    - "--scanpy-corr-method"
    - "--scanpy-pts"
    - "--scanpy-rankby-abs"
    - "--scanpy-tie-correct"
    param_hints:
      wilcoxon:
        priority: "groupby → scanpy_corr_method → filter_markers → scanpy_tie_correct"
        params: ["groupby", "group1", "group2", "n_top_genes", "fdr_threshold", "log2fc_threshold",
          "scanpy_corr_method", "scanpy_rankby_abs", "scanpy_pts", "scanpy_tie_correct",
          "filter_markers", "min_in_group_fraction", "min_fold_change", "max_out_group_fraction",
          "filter_compare_abs"]
        defaults: {groupby: "leiden", n_top_genes: 10, fdr_threshold: 0.05, log2fc_threshold: 1.0,
          scanpy_corr_method: "benjamini-hochberg", scanpy_rankby_abs: false, scanpy_pts: false,
          scanpy_tie_correct: false, filter_markers: true, min_in_group_fraction: 0.25,
          min_fold_change: 1.0, max_out_group_fraction: 0.5, filter_compare_abs: false}
        requires: ["obs.groupby", "X_log_normalized"]
        tips:
        - "--scanpy-corr-method: official `scanpy.tl.rank_genes_groups` multiple-testing
          correction (`benjamini-hochberg` or `bonferroni`)."
        - "--scanpy-tie-correct: official Wilcoxon tie correction toggle in Scanpy;
          only relevant for `wilcoxon`."
        - "--scanpy-rankby-abs: ranks genes by absolute score but does not change
          the reported log fold-change sign."
        - "--scanpy-pts: asks Scanpy to report per-group detection fractions (`pct_nz_group`,
          `pct_nz_reference`)."
        - "--filter-markers + min/max fraction controls: official `scanpy.tl.filter_rank_genes_groups`
          post-filter for cluster-style marker specificity."
      t-test:
        priority: "groupby → scanpy_corr_method → filter_markers"
        params: ["groupby", "group1", "group2", "n_top_genes", "fdr_threshold", "log2fc_threshold",
          "scanpy_corr_method", "scanpy_rankby_abs", "scanpy_pts", "filter_markers",
          "min_in_group_fraction", "min_fold_change", "max_out_group_fraction", "filter_compare_abs"]
        defaults: {groupby: "leiden", n_top_genes: 10, fdr_threshold: 0.05, log2fc_threshold: 1.0,
          scanpy_corr_method: "benjamini-hochberg", scanpy_rankby_abs: false, scanpy_pts: false,
          filter_markers: true, min_in_group_fraction: 0.25, min_fold_change: 1.0,
          max_out_group_fraction: 0.5, filter_compare_abs: false}
        requires: ["obs.groupby", "X_log_normalized"]
        tips:
        - "--scanpy-corr-method / --scanpy-rankby-abs / --scanpy-pts: same official
          Scanpy controls as the Wilcoxon path."
        - "--filter-markers: keep this on for a first pass unless the user explicitly
          wants raw unfiltered ranking output."
        - "`t-test` is faster than Wilcoxon but remains an exploratory log-expression
          marker workflow rather than replicate-aware sample inference."
      pydeseq2:
        priority: "group1/group2 → sample_key → min_cells_per_sample/min_counts_per_gene
          → pydeseq2_fit_type/size_factors_fit_type → pydeseq2_alpha"
        params: ["groupby", "group1", "group2", "sample_key", "n_top_genes", "fdr_threshold",
          "log2fc_threshold", "min_cells_per_sample", "min_counts_per_gene", "pydeseq2_fit_type",
          "pydeseq2_size_factors_fit_type", "pydeseq2_refit_cooks", "pydeseq2_alpha",
          "pydeseq2_cooks_filter", "pydeseq2_independent_filter", "pydeseq2_n_cpus"]
        defaults: {groupby: "leiden", sample_key: "sample_id", n_top_genes: 10, fdr_threshold: 0.05,
          log2fc_threshold: 1.0, min_cells_per_sample: 10, min_counts_per_gene: 10,
          pydeseq2_fit_type: "parametric", pydeseq2_size_factors_fit_type: "ratio",
          pydeseq2_refit_cooks: true, pydeseq2_alpha: 0.05, pydeseq2_cooks_filter: true,
          pydeseq2_independent_filter: true, pydeseq2_n_cpus: 1}
        requires: ["counts_or_raw", "obs.sample_key", "obs.groupby"]
        tips:
        - "`pydeseq2` in `spatial-de` is intentionally restricted to explicit two-group
          contrasts with a real `sample_key`; OmicsClaw will not fabricate replicates."
        - "If the same biological samples contribute to both groups, OmicsClaw automatically
          uses a paired design (`~ sample_id + condition`)."
        - "--min-cells-per-sample: wrapper-level gate for each sample x group pseudobulk
          profile before DESeq2 fitting."
        - "--min-counts-per-gene: wrapper-level pseudobulk gene filter applied before
          PyDESeq2."
        - "--pydeseq2-fit-type / --pydeseq2-size-factors-fit-type / --pydeseq2-refit-cooks
          / --pydeseq2-alpha / --pydeseq2-cooks-filter / --pydeseq2-independent-filter
          / --pydeseq2-n-cpus: official PyDESeq2 controls exposed directly by the
          wrapper."
    legacy_aliases: [de]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
      - python3
      env: []
      config: []
    emoji: "🧬"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
    - kind: pip
      package: scanpy
      bins: []
    - kind: pip
      package: pydeseq2
      bins: []
    trigger_keywords:
    - differential expression
    - marker gene
    - pseudobulk
    - Wilcoxon
    - t-test
    - PyDESeq2
    - spatial DE
    script: spatial_de.py
---

# 🧬 Spatial DE

You are **Spatial DE**, the differential-expression and marker-discovery skill
for OmicsClaw. Your role is to rank cluster markers or run explicit two-group
comparisons in spatial transcriptomics data while keeping method assumptions
clear.

## Why This Exists

- **Without it**: users often mix exploratory spot-level marker ranking with
  replicate-aware differential expression and end up over-interpreting the
  result.
- **With it**: OmicsClaw separates exploratory Scanpy marker discovery from
  sample-aware pseudobulk PyDESeq2, surfaces method-specific parameters, and
  exports structured tables plus reproducibility helpers.
- **Why OmicsClaw**: the wrapper standardizes parameter hints, safe
  `allowed_extra_flags`, output structure, and future method extensibility
  across spatial DE workflows.

## Core Capabilities

1. **Wilcoxon markers**: non-parametric Scanpy marker discovery on
   log-normalized expression.
2. **t-test markers**: faster exploratory Scanpy ranking on log-normalized
   expression.
3. **Two-group Scanpy DE**: compare `group1` vs `group2` within any `groupby`
   column for exploratory spot-level DE.
4. **Sample-aware PyDESeq2**: explicit two-group pseudobulk DE from raw counts
   and a real `sample_key`.
5. **Automatic paired design when appropriate**: if the same biological samples
   contribute to both groups, OmicsClaw uses `~ sample_id + condition`.
6. **Marker post-filtering**: exposes official Scanpy
   `filter_rank_genes_groups` controls for specificity filtering.
7. **Standard Python gallery**: emits a recipe-driven DE gallery with
   overview, diagnostic, supporting, and uncertainty panels backed by the
   shared `skills/spatial/_lib/viz` layer.
8. **Figure-ready exports**: writes `figure_data/` CSVs plus a gallery manifest
   so downstream tools can restyle the same DE result without recomputing it.
9. **Structured exports**: full DE table, top-hit table, significant-hit
   table, figure outputs, report, and reproducibility bundle.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `adata.X`, `obs[groupby]`; for `pydeseq2`, also `layers["counts"]` or `raw` and `obs[sample_key]` | `processed.h5ad` |
| Demo | n/a | `--demo` flag | Runs spatial-preprocess demo, then injects synthetic sample IDs |

## Input Matrix Convention

Different DE methods have different statistical assumptions. OmicsClaw keeps
them separate:

| Method | Input Matrix | Rationale |
|--------|-------------|-----------|
| `wilcoxon` | `adata.X` (log-normalized) | `scanpy.tl.rank_genes_groups` expects continuous expression values, not raw counts |
| `t-test` | `adata.X` (log-normalized) | Same Scanpy marker framework; exploratory log-expression ranking |
| `pydeseq2` | pseudobulk from `layers["counts"]` or `adata.raw` | PyDESeq2 models raw integer-like counts with a negative-binomial GLM |

**Core rule**:

- Use `wilcoxon` / `t-test` for exploratory marker ranking on normalized
  expression.
- Use `pydeseq2` only when you have a meaningful `sample_key` that represents
  biological replicates.

**Recommended preprocessing layout**:

```python
adata.layers["counts"] = adata.X.copy()   # before normalize_total + log1p
adata.X = lognorm_expr                     # after normalize_total + log1p
adata.obs["leiden"] = cluster_labels
adata.obs["sample_id"] = biological_sample_ids
```

If `layers["counts"]` is missing, OmicsClaw falls back to `adata.raw` or
`adata.X` with a warning.

## Workflow

1. **Load**: read the preprocessed h5ad.
2. **Validate**: confirm `groupby` exists; if the default `leiden` is missing,
   OmicsClaw can compute a minimal clustering pass.
3. **Choose the method**:
   - `wilcoxon` / `t-test`: exploratory Scanpy marker discovery
   - `pydeseq2`: explicit two-group pseudobulk sample-aware DE
4. **Run the test**:
   - Scanpy: `rank_genes_groups(...)` plus optional
     `filter_rank_genes_groups(...)`
   - PyDESeq2: build sample x group pseudobulk profiles, choose paired or
     unpaired design, then fit `DeseqDataSet` / `DeseqStats`
5. **Render the standard gallery**: build the OmicsClaw narrative gallery with
   grouping context, volcano diagnostics, top-hit summaries, and uncertainty
   panels.
6. **Export figure-ready data**: write `figure_data/*.csv` and
   `figure_data/manifest.json` for downstream customization.
7. **Export**: write `markers_top.csv`, `de_full.csv`, `de_significant.csv`,
   `report.md`, `result.json`, figures, and reproducibility helpers.

## Visualization Contract

OmicsClaw treats `spatial-de` visualization as a two-layer system:

1. **Python standard gallery**: the canonical result layer. This is the
   default output users should inspect first.
2. **R customization layer**: an optional styling and publication layer that
   reads `figure_data/` and does not recompute Scanpy ranking or PyDESeq2.

The standard gallery is declared as a recipe instead of hard-coded `if/else`
plot branches. Current gallery roles include:

- `overview`: grouping labels on tissue, top-marker dotplots, and volcano
  overviews of the strongest DE comparisons
- `diagnostic`: group-level DE burden projected onto spatial and UMAP views
- `supporting`: top-hit barplots, group-burden summaries, and marker heatmaps
- `uncertainty`: adjusted p-value distributions, pseudobulk sample support, and
  skipped sample-group summaries when applicable

## CLI Reference

```bash
# Default exploratory marker discovery
oc run spatial-de \
  --input <processed.h5ad> --output <dir>

# Wilcoxon with richer Scanpy controls
oc run spatial-de \
  --input <processed.h5ad> --method wilcoxon \
  --groupby leiden --scanpy-corr-method benjamini-hochberg \
  --scanpy-pts --filter-markers \
  --min-in-group-fraction 0.25 --min-fold-change 1.0 \
  --max-out-group-fraction 0.5 --output <dir>

# Pairwise Scanpy comparison
oc run spatial-de \
  --input <processed.h5ad> --method t-test \
  --groupby leiden --group1 0 --group2 1 \
  --n-top-genes 20 --output <dir>

# Sample-aware pseudobulk DE with PyDESeq2
oc run spatial-de \
  --input <processed.h5ad> --method pydeseq2 \
  --groupby leiden --group1 0 --group2 1 \
  --sample-key sample_id \
  --min-cells-per-sample 10 --min-counts-per-gene 10 \
  --pydeseq2-fit-type parametric \
  --pydeseq2-size-factors-fit-type ratio \
  --pydeseq2-alpha 0.05 --pydeseq2-n-cpus 1 \
  --output <dir>

# Demo mode
oc run spatial-de --demo --output /tmp/de_demo

# Direct script entrypoint
python skills/spatial/spatial-de/spatial_de.py \
  --input <processed.h5ad> --method wilcoxon --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Find marker genes for all my spatial clusters with Wilcoxon"
- "Compare cluster 0 vs cluster 1 with sample-aware pseudobulk"
- "Run a fast t-test marker pass before I decide whether I need DESeq2"

## Algorithm / Methodology

### Wilcoxon

1. **Input**: `adata.X` (log-normalized expression)
2. **Test**: `scanpy.tl.rank_genes_groups(..., method="wilcoxon")`
3. **Optional tie correction**: `scanpy_tie_correct`
4. **Multiple testing**: `scanpy_corr_method`
5. **Optional marker filter**:
   `scanpy.tl.filter_rank_genes_groups(...)`

**Core tuning flags**:

- `--groupby`
- `--group1 / --group2` for explicit pairwise mode
- `--scanpy-corr-method`
- `--scanpy-rankby-abs`
- `--scanpy-pts`
- `--scanpy-tie-correct`
- `--filter-markers`
- `--min-in-group-fraction`
- `--min-fold-change`
- `--max-out-group-fraction`
- `--filter-compare-abs`

### t-test

1. **Input**: `adata.X` (log-normalized expression)
2. **Test**: `scanpy.tl.rank_genes_groups(..., method="t-test")`
3. **Post-filter**: same optional Scanpy marker filtering layer as Wilcoxon

**Use case**: quick exploratory marker ranking when the user wants a fast first
pass and accepts stronger parametric assumptions.

### PyDESeq2

1. **Input**: raw counts aggregated to sample x group pseudobulk profiles
2. **Design choice**:
   - `~ condition` if each sample belongs to only one compared group
   - `~ sample_id + condition` if the same samples contribute to both groups
3. **Model**: `DeseqDataSet(...)` + `DeseqStats(...)`
4. **Contrast direction**: OmicsClaw uses `contrast=["condition", group1, group2]`
5. **Outputs**: `log2fc`, `pvalue_adj`, `stat`, and significance/effect-size
   helper columns

**Core tuning flags**:

- `--groupby`
- `--group1`
- `--group2`
- `--sample-key`
- `--min-cells-per-sample`
- `--min-counts-per-gene`
- `--pydeseq2-fit-type`
- `--pydeseq2-size-factors-fit-type`
- `--pydeseq2-refit-cooks`
- `--pydeseq2-alpha`
- `--pydeseq2-cooks-filter`
- `--pydeseq2-independent-filter`
- `--pydeseq2-n-cpus`

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── de_group_spatial_context.png
│   ├── de_marker_dotplot.png
│   ├── de_volcano.png
│   ├── de_effect_burden_spatial.png
│   ├── de_effect_burden_umap.png
│   ├── de_marker_heatmap.png
│   ├── de_top_hits_barplot.png
│   ├── group_de_burden.png
│   ├── de_pvalue_distribution.png
│   ├── sample_counts_by_group.png      # PyDESeq2 when sample support exists
│   ├── skipped_sample_groups.png       # PyDESeq2 when sample-group combos were skipped
│   └── manifest.json
├── figure_data/
│   ├── markers_top.csv
│   ├── top_de_hits.csv
│   ├── de_full.csv
│   ├── de_plot_points.csv
│   ├── de_significant.csv
│   ├── group_de_metrics.csv
│   ├── de_run_summary.csv
│   ├── sample_counts_by_group.csv
│   ├── skipped_sample_groups.csv
│   ├── de_spatial_points.csv
│   ├── de_umap_points.csv              # when UMAP is available
│   └── manifest.json
├── tables/
│   ├── markers_top.csv
│   ├── de_full.csv
│   ├── de_significant.csv
│   ├── group_de_metrics.csv
│   ├── sample_counts_by_group.csv
│   └── skipped_sample_groups.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── requirements.txt
    └── r_visualization.sh
```

The bundled optional R templates live under:

```text
skills/spatial/spatial-de/r_visualization/
├── README.md
└── de_publication_template.R
```

## Safety

- **Local-first**: no data upload.
- **Method separation**: do not describe Scanpy marker ranking and pseudobulk
  PyDESeq2 as interchangeable evidence.
- **No fake replicates**: `pydeseq2` requires a real `sample_key` and does not
  random-split cells into pseudo-samples.
- **Audit trail**: key parameters and workflow metadata are written to the
  report, result JSON, and reproducibility bundle.

## Dependencies

**Required**:

- `scanpy`

**Optional (Python)**:

- `pydeseq2`

**Optional (R)**:

- `ggplot2`

## Integration with Orchestrator

**Trigger conditions**:

- differential expression
- marker genes
- cluster markers
- Wilcoxon
- t-test
- pseudobulk
- PyDESeq2

**Chaining**:

- Usually consumes `processed.h5ad` from `spatial-preprocess`
- For explicit condition-focused replicate-aware comparisons, consider
  `spatial-condition`

## Citations

- [Scanpy `rank_genes_groups`](https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html)
- [Scanpy `filter_rank_genes_groups`](https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.filter_rank_genes_groups.html)
- [PyDESeq2 `DeseqDataSet`](https://pydeseq2.readthedocs.io/en/stable/api/docstrings/pydeseq2.dds.DeseqDataSet.html)
- [PyDESeq2 `DeseqStats`](https://pydeseq2.readthedocs.io/en/stable/api/docstrings/pydeseq2.ds.DeseqStats.html)
