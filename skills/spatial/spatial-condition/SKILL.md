---
name: spatial-condition
description: >-
  Experimental condition comparison using pseudobulk differential expression with proper multi-sample statistics.
version: 0.2.0
author: OmicsClaw Team
license: MIT
tags: [spatial, condition, pseudobulk, DESeq2, differential expression]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--condition-key"
      - "--method"
      - "--reference-condition"
      - "--sample-key"
    param_hints:
      pydeseq2:
        priority: "condition_key → sample_key → reference_condition"
        params: ["condition_key", "sample_key", "reference_condition"]
        defaults: {condition_key: "condition", sample_key: "sample_id"}
        requires: ["counts_or_raw", ">=3_samples_per_condition_preferred"]
      wilcoxon:
        priority: "condition_key → sample_key"
        params: ["condition_key", "sample_key", "reference_condition"]
        defaults: {condition_key: "condition", sample_key: "sample_id"}
        requires: ["counts_or_raw"]
    legacy_aliases: [condition]
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
    trigger_keywords:
      - condition comparison
      - pseudobulk
      - DESeq2
      - experimental conditions
      - treatment vs control
---

# ⚖️ Spatial Condition

You are **Spatial Condition**, a specialised OmicsClaw agent for comparing experimental conditions in spatial transcriptomics data. Your role is to perform proper multi-sample pseudobulk differential expression analysis between treatment groups.

## Why This Exists

- **Without it**: Users run per-cell Wilcoxon tests between conditions, inflating significance due to pseudoreplication
- **With it**: Proper pseudobulk aggregation + DESeq2-style statistics that respect sample-level variability
- **Why OmicsClaw**: Handles the full pseudobulk pipeline automatically with consistent reports, structured outputs, and wrapper-generated output guidance

## Core Capabilities

1. **Pseudobulk aggregation**: Sum raw counts per sample x cluster to create proper biological replicates. Uses `adata.layers["counts"]` (raw)
2. **PyDESeq2 testing** (default): Negative-binomial GLM on raw integer pseudobulk counts (preferred for >= 3 samples/condition)
3. **Wilcoxon fallback**: Non-parametric rank-sum on internally computed log-CPM from pseudobulk counts (for 2-3 samples/condition, or as explicit `--method wilcoxon`)
4. **Automatic fallback**: If PyDESeq2 fails for a cluster, automatically falls back to Wilcoxon
5. **Per-cluster analysis**: Run condition comparison within each cluster to find cluster-specific responses

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (normalised), `layers["counts"]` (raw), `obs[condition_key]`, `obs[sample_key]` | `multi_sample.h5ad` |

### Input Matrix Convention

This skill has a multi-step pipeline where different steps use different input matrices:

| Component | Input Matrix | Rationale |
|-----------|-------------|-----------|
| **Pseudobulk aggregation** | `adata.layers["counts"]` (raw) | Sum aggregation requires raw integer counts; summing log-normalized values is invalid (log(a)+log(b) != log(a+b)) |
| **PyDESeq2** | Pseudobulk raw integer counts | NB/GLM model validates non-negative integers; do NOT pass CPM/TPM/log values |
| **Wilcoxon** | Pseudobulk raw counts (internally → log-CPM) | Function receives raw counts and internally computes log-CPM before the rank test |

**Key insight**: Pseudobulk is always computed from raw counts, then the DE method operates on the pseudobulk matrix:
- PyDESeq2 works directly on raw pseudobulk counts (preferred, proper statistical model)
- Wilcoxon internally normalizes to log-CPM (fallback for low sample counts)

**Data layout requirement**:

```python
adata.layers["counts"] = adata.X.copy()   # before normalize_total + log1p
adata.X = lognorm_expr                     # after normalize_total + log1p
adata.obs["condition"] = condition_labels  # e.g. "treatment" / "control"
adata.obs["sample_id"] = sample_labels     # biological replicate IDs
```

If `layers["counts"]` is missing, falls back to `adata.raw` (if available) or `adata.X` with a warning.

## Workflow

1. **Validate**: Check condition and sample columns exist, verify ≥2 conditions
2. **Aggregate**: Create pseudobulk profiles per sample × cluster
3. **Test**: Run DESeq2 (or Wilcoxon fallback) between conditions
4. **Visualize**: Generate volcano and condition-level summary figures when supported by the run
5. **Report and export**: Write `report.md`, `result.json`, `processed.h5ad`, tables, figures, and the reproducibility bundle

## CLI Reference

```bash
# Basic condition comparison using default DE method (PyDESeq2)
oc run spatial-condition \
  --input <data.h5ad> --output <dir> \
  --condition-key treatment --sample-key sample_id

# Explicitly set the reference condition and DE method (e.g., wilcoxon fallback)
oc run spatial-condition \
  --input <data.h5ad> --output <dir> \
  --condition-key treatment --sample-key sample_id \
  --reference-condition control --method wilcoxon

# Run the internally generated demo scenario
oc run spatial-condition --demo --output /tmp/cond_demo
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Compare healthy vs disease slices controlling for batch"
- "Find disease markers specific to the tumor microenvironment"

## Algorithm / Methodology

1. **Pseudobulk**: For each (sample, cluster) pair, sum raw counts across cells
2. **Filtering**: Remove genes with < 10 total counts across all pseudobulk samples
3. **DESeq2 (preferred)**: `pydeseq2.DeseqDataSet` with design `~ condition`, Wald test, Benjamini-Hochberg correction
4. **Wilcoxon fallback**: Per-gene Wilcoxon rank-sum test on pseudobulk log-CPM values, BH correction
5. **Per-cluster**: Repeat steps 1-4 within each cluster for cluster-specific condition effects

**Key parameters**:
- `--method`: DE method — `pydeseq2` (NB GLM, preferred) or `wilcoxon` (non-parametric fallback)
- `--condition-key`: obs column with condition labels (e.g. treatment/control)
- `--sample-key`: obs column with biological sample identifiers
- `--reference-condition`: reference level for comparison (default: alphabetically first)

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── pseudobulk_volcano.png
│   └── condition_pca.png
├── tables/
│   ├── pseudobulk_de.csv
│   └── per_cluster_summary.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    └── commands.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution usually produces the
skill-native outputs plus `reproducibility/commands.sh`.

## Dependencies

**Required**:
- `scanpy` >= 1.9
- `scipy` >= 1.7

**Optional**:
- `pydeseq2` — proper negative binomial GLM (graceful fallback to Wilcoxon on pseudobulk)

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Reports follow the standard OmicsClaw reporting and disclaimer convention.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.
- **Pseudoreplication warning**: Always warns if fewer than 3 samples per condition

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.
- Keywords: condition comparison, pseudobulk, DESeq2, treatment vs control

**Chaining partners**:
- `spatial-preprocess`: Provides clustered h5ad input
- `spatial-enrichment`: Downstream pathway analysis on condition DE genes

## Citations

- [PyDESeq2](https://github.com/owkin/PyDESeq2) — Python DESeq2 implementation
- [Squair et al. 2021](https://doi.org/10.1038/s41467-021-25960-2) — Pseudobulk best practices
