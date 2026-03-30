---
name: spatial-condition
description: >-
  Compare experimental conditions in spatial transcriptomics data using
  pseudobulk differential expression with method-aware PyDESeq2 or Wilcoxon
  testing and explicit replicate handling.
version: 0.3.0
author: OmicsClaw Team
license: MIT
tags: [spatial, condition, pseudobulk, pydeseq2, DESeq2, differential-expression, wilcoxon]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--cluster-key"
      - "--condition-key"
      - "--fdr-threshold"
      - "--log2fc-threshold"
      - "--method"
      - "--min-counts-per-gene"
      - "--min-samples-per-condition"
      - "--no-pydeseq2-cooks-filter"
      - "--no-pydeseq2-independent-filter"
      - "--no-pydeseq2-refit-cooks"
      - "--pydeseq2-alpha"
      - "--pydeseq2-cooks-filter"
      - "--pydeseq2-fit-type"
      - "--pydeseq2-independent-filter"
      - "--pydeseq2-n-cpus"
      - "--pydeseq2-refit-cooks"
      - "--pydeseq2-size-factors-fit-type"
      - "--reference-condition"
      - "--sample-key"
      - "--wilcoxon-alternative"
    param_hints:
      pydeseq2:
        priority: "condition_key/sample_key/cluster_key → reference_condition → pydeseq2_fit_type/size_factors_fit_type → pydeseq2_alpha"
        params: ["condition_key", "sample_key", "cluster_key", "reference_condition", "min_counts_per_gene", "min_samples_per_condition", "fdr_threshold", "log2fc_threshold", "pydeseq2_fit_type", "pydeseq2_size_factors_fit_type", "pydeseq2_alpha", "pydeseq2_refit_cooks", "pydeseq2_cooks_filter", "pydeseq2_independent_filter", "pydeseq2_n_cpus"]
        defaults: {condition_key: "condition", sample_key: "sample_id", cluster_key: "leiden", min_counts_per_gene: 10, min_samples_per_condition: 2, fdr_threshold: 0.05, log2fc_threshold: 1.0, pydeseq2_fit_type: "parametric", pydeseq2_size_factors_fit_type: "ratio", pydeseq2_alpha: 0.05, pydeseq2_refit_cooks: true, pydeseq2_cooks_filter: true, pydeseq2_independent_filter: true, pydeseq2_n_cpus: 1}
        requires: ["raw_or_counts", "obs.condition_key", "obs.sample_key"]
        tips:
          - "--condition-key / --sample-key / --cluster-key: define the pseudobulk design before any statistical tuning."
          - "--reference-condition: determines the direction of the contrast and therefore the sign of log2FC."
          - "--min-counts-per-gene: OmicsClaw pseudobulk gene filter before DE testing."
          - "--min-samples-per-condition: wrapper-level replicate gate; use 2 as the minimum and prefer >=3."
          - "--pydeseq2-fit-type: official PyDESeq2 dispersion fit mode (`parametric` or `mean`)."
          - "--pydeseq2-size-factors-fit-type: official PyDESeq2 size-factor strategy (`ratio`, `poscounts`, `iterative`)."
          - "--pydeseq2-alpha: official DeseqStats significance target used during result filtering."
          - "--pydeseq2-refit-cooks / --pydeseq2-cooks-filter / --pydeseq2-independent-filter: official PyDESeq2 result-stabilizing controls."
          - "--pydeseq2-n-cpus: passed through to DeseqDataSet / DeseqStats."
      wilcoxon:
        priority: "condition_key/sample_key/cluster_key → reference_condition → wilcoxon_alternative"
        params: ["condition_key", "sample_key", "cluster_key", "reference_condition", "min_counts_per_gene", "min_samples_per_condition", "fdr_threshold", "log2fc_threshold", "wilcoxon_alternative"]
        defaults: {condition_key: "condition", sample_key: "sample_id", cluster_key: "leiden", min_counts_per_gene: 10, min_samples_per_condition: 2, fdr_threshold: 0.05, log2fc_threshold: 1.0, wilcoxon_alternative: "two-sided"}
        requires: ["raw_or_counts", "obs.condition_key", "obs.sample_key"]
        tips:
          - "--wilcoxon-alternative: official SciPy `ranksums` alternative hypothesis (`two-sided`, `less`, `greater`)."
          - "--reference-condition: controls the comparison direction; OmicsClaw still reports log2FC relative to the reference."
          - "--min-samples-per-condition: keep this at >=2; Wilcoxon is a fallback, not a replacement for proper replicate-rich GLM analyses."
    legacy_aliases: [condition, spatial-condition]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "⚖️"
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
      - condition comparison
      - pseudobulk
      - DESeq2
      - PyDESeq2
      - treatment vs control
      - experimental conditions
      - replicate-aware differential expression
---

# ⚖️ Spatial Condition

You are **Spatial Condition**, the condition-comparison skill for OmicsClaw.
Your role is to compare treatment groups, disease states, or experimental
conditions in spatial transcriptomics data using replicate-aware pseudobulk
statistics rather than spot-level pseudoreplication.

## Why This Exists

- **Without it**: users often compare conditions with cell/spot-level Wilcoxon
  tests, which inflates significance by treating technical observations as
  independent biological replicates.
- **With it**: OmicsClaw aggregates counts to sample-level pseudobulk profiles
  and applies either a proper negative-binomial GLM (`pydeseq2`) or an explicit
  Wilcoxon fallback.
- **Why OmicsClaw**: it standardizes design-column validation, replicate checks,
  method-specific tuning hints, and reproducible outputs across spatial
  condition-comparison workflows.

## Core Capabilities

1. **Pseudobulk aggregation**: sums raw counts per sample x cluster.
2. **PyDESeq2** (default): negative-binomial GLM on pseudobulk counts using
   official PyDESeq2 controls.
3. **Wilcoxon fallback**: pseudobulk rank-sum testing on log-CPM transformed
   profiles for lower-replicate or fallback scenarios.
4. **Per-cluster contrasts**: runs condition comparisons within each cluster to
   find context-specific responses.
5. **Replicate-aware filtering**: skips contrasts that do not satisfy the
   configured sample-count threshold.
6. **Standard Python gallery**: emits a recipe-driven condition-comparison
   gallery with overview, diagnostic, supporting, and uncertainty panels backed
   by the shared `skills/spatial/_lib/viz` layer.
7. **Figure-ready exports**: writes `figure_data/` CSVs plus a gallery manifest
   so downstream tools can restyle the same analysis without recomputing DE.
8. **Structured outputs**: exports global DE table, per-cluster contrast
   summaries, skipped-contrast reasons, figures, and reproducibility commands.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `layers["counts"]` or `raw`, `obs[condition_key]`, `obs[sample_key]` | `multi_sample.h5ad` |
| Demo | n/a | `--demo` flag | Runs spatial-preprocess demo then injects synthetic conditions / replicate IDs |

### Input Matrix Convention

This skill has a multi-step pipeline with different statistical assumptions:

| Component | Input Matrix | Rationale |
|-----------|-------------|-----------|
| **Pseudobulk aggregation** | `adata.layers["counts"]` (raw) | Sum aggregation requires raw integer-like counts; summing log values is invalid |
| **PyDESeq2** | pseudobulk raw integer counts | PyDESeq2 models counts with a negative-binomial GLM |
| **Wilcoxon** | pseudobulk raw counts internally transformed to CPM/log-space | OmicsClaw computes the transformation inside the wrapper before rank testing |

**Core principle**: pseudobulk always starts from raw counts, then the DE method
operates on the aggregated matrix.

**Data layout requirement**:

```python
adata.layers["counts"] = adata.X.copy()    # before normalize_total + log1p
adata.X = lognorm_expr                      # after normalize_total + log1p
adata.obs["condition"] = condition_labels   # e.g. "treated" / "control"
adata.obs["sample_id"] = sample_labels      # biological replicate IDs
```

If `layers["counts"]` is missing, OmicsClaw falls back to `adata.raw` or
`adata.X` with a warning.

## Workflow

1. **Validate**: check condition / sample columns and verify each sample maps to
   exactly one condition.
2. **Aggregate**: create pseudobulk matrices per sample x cluster from raw
   counts.
3. **Filter**: drop low-count genes and skip contrasts with too few biological
   replicates.
4. **Test**:
   - `pydeseq2`: fit NB GLM per cluster/contrast
   - `wilcoxon`: run rank-sum test on transformed pseudobulk profiles
5. **Render the standard gallery**: build the OmicsClaw narrative gallery with
   design-context, diagnostic burden, supporting summaries, and uncertainty
   panels.
6. **Export figure-ready data**: write `figure_data/*.csv` and
   `figure_data/manifest.json` for downstream customization.
7. **Report and export**: write `report.md`, `result.json`, `processed.h5ad`,
   figures, tables, and reproducibility helpers.

## Visualization Contract

OmicsClaw treats `spatial-condition` visualization as a two-layer system:

1. **Python standard gallery**: the canonical result layer. This is the
   default output users should inspect first.
2. **R customization layer**: an optional styling and publication layer that
   reads `figure_data/` and does not recompute pseudobulk DE.

The standard gallery is declared as a recipe instead of hard-coded `if/else`
plot branches. Current gallery roles include:

- `overview`: condition labels on tissue and a global pseudobulk volcano
- `diagnostic`: cluster-level DE burden projected onto spatial and UMAP views
- `supporting`: per-contrast significant-gene counts and per-cluster burden
- `uncertainty`: adjusted p-value distributions, sample support, and
  skipped-contrast summaries when applicable

## CLI Reference

```bash
# PyDESeq2 default run
oc run spatial-condition \
  --input <data.h5ad> --output <dir> \
  --condition-key condition --sample-key sample_id

# PyDESeq2 with explicit cluster labels and tuning
oc run spatial-condition \
  --input <data.h5ad> --method pydeseq2 \
  --condition-key condition --sample-key sample_id --cluster-key leiden \
  --reference-condition control \
  --min-counts-per-gene 10 --min-samples-per-condition 2 \
  --pydeseq2-fit-type parametric \
  --pydeseq2-size-factors-fit-type ratio \
  --pydeseq2-alpha 0.05 --pydeseq2-n-cpus 1 \
  --output <dir>

# Wilcoxon fallback mode
oc run spatial-condition \
  --input <data.h5ad> --method wilcoxon \
  --condition-key condition --sample-key sample_id \
  --reference-condition control \
  --wilcoxon-alternative two-sided \
  --output <dir>

# Demo mode
oc run spatial-condition --demo --output /tmp/cond_demo

# Direct script entrypoint
python skills/spatial/spatial-condition/spatial_condition.py \
  --input <data.h5ad> --method pydeseq2 --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Compare healthy vs disease slices with pseudobulk statistics"
- "Find treatment-responsive genes per spatial cluster"
- "Run a Wilcoxon fallback because I only have two replicates per condition"

## Algorithm / Methodology

### PyDESeq2 (default)

1. **Input**: pseudobulk raw integer counts built from sample x cluster
   aggregation
2. **Design**: OmicsClaw fits `~ condition` using official `DeseqDataSet(...)`
   controls
3. **Testing**: OmicsClaw uses `DeseqStats(...)` with explicit
   `contrast=["condition", other, reference]`
4. **Outputs**: reports `base_mean`, `log2fc`, `stat`, `pvalue`, and adjusted
   `pvalue_adj`

**Core tuning flags**:

- `--reference-condition`: defines the sign direction of the contrast
- `--cluster-key`: chooses the cluster partition for per-cluster pseudobulk
- `--min-counts-per-gene`: wrapper-level gene filter before DE testing
- `--min-samples-per-condition`: wrapper-level replicate gate
- `--pydeseq2-fit-type`: official PyDESeq2 dispersion fit mode
- `--pydeseq2-size-factors-fit-type`: official normalization size-factor mode
- `--pydeseq2-refit-cooks`: whether Cook's outlier refitting is enabled
- `--pydeseq2-alpha`: official target FDR used by `DeseqStats`
- `--pydeseq2-cooks-filter`: whether Cook's filtering is applied in result
  extraction
- `--pydeseq2-independent-filter`: whether independent filtering is applied in
  result extraction
- `--pydeseq2-n-cpus`: CPU count passed to PyDESeq2

### Wilcoxon

1. **Input**: pseudobulk raw counts
2. **Transformation**: OmicsClaw computes CPM/log-transformed profiles inside
   the wrapper
3. **Testing**: `scipy.stats.ranksums()` is used on per-gene transformed values
4. **Outputs**: reports a pseudobulk-derived `log2fc`, Wilcoxon statistic, raw
   `pvalue`, and BH-adjusted `pvalue_adj`

**Core tuning flags**:

- `--reference-condition`: defines the sign direction of the contrast
- `--cluster-key`: chooses the cluster partition for per-cluster pseudobulk
- `--min-counts-per-gene`: wrapper-level gene filter before DE testing
- `--min-samples-per-condition`: minimum replicate count before a contrast is
  attempted
- `--wilcoxon-alternative`: official SciPy alternative hypothesis

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── condition_spatial_context.png
│   ├── pseudobulk_volcano.png
│   ├── condition_effect_burden_spatial.png
│   ├── condition_effect_burden_umap.png
│   ├── condition_de_barplot.png
│   ├── cluster_de_burden.png
│   ├── condition_pvalue_distribution.png
│   ├── sample_counts_by_condition.png
│   └── manifest.json
├── figure_data/
│   ├── pseudobulk_de.csv
│   ├── pseudobulk_volcano_points.csv
│   ├── per_cluster_summary.csv
│   ├── skipped_contrasts.csv
│   ├── cluster_de_metrics.csv
│   ├── top_de_genes.csv
│   ├── sample_counts_by_condition.csv
│   ├── condition_run_summary.csv
│   ├── condition_spatial_points.csv
│   ├── condition_umap_points.csv          # when UMAP is available
│   └── manifest.json
├── tables/
│   ├── pseudobulk_de.csv
│   ├── per_cluster_summary.csv
│   └── skipped_contrasts.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── requirements.txt
    └── r_visualization.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution usually produces the
skill-native outputs plus `reproducibility/commands.sh`.

The bundled optional R templates live under:

```text
skills/spatial/spatial-condition/r_visualization/
├── README.md
└── condition_publication_template.R
```

## Dependencies

**Required**:

- `scanpy`
- `scipy`

**Optional**:

- `pydeseq2` for proper negative-binomial GLM inference

**Optional (R)**:

- `ggplot2`

## Safety

- **Local-first**: all processing remains local.
- **No pseudoreplication**: do not interpret spot-level observations as
  biological replicates.
- **Reference transparency**: always state which condition is the reference
  before interpreting log2 fold changes.
- **Replicate caution**: fewer than 3 samples per condition is workable but
  materially less stable.

## Integration with Orchestrator

**Trigger conditions**:

- condition comparison
- pseudobulk
- PyDESeq2 / DESeq2
- treatment vs control

**Chaining partners**:

- `spatial-preprocess` for counts preservation and baseline clustering
- `spatial-enrichment` for pathway analysis on DE genes
- `spatial-genes` for comparing treatment-responsive genes to SVG programs

## Citations

- [PyDESeq2 documentation: `DeseqDataSet`](https://pydeseq2.readthedocs.io/en/stable/api/docstrings/pydeseq2.dds.DeseqDataSet.html)
- [PyDESeq2 documentation: `DeseqStats`](https://pydeseq2.readthedocs.io/en/stable/api/docstrings/pydeseq2.ds.DeseqStats.html)
- [SciPy documentation: `scipy.stats.ranksums`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ranksums.html)
- [Squair et al. 2021](https://doi.org/10.1038/s41467-021-25960-2) — pseudobulk best practices
