---
doc_id: skill-guide-sc-filter
title: OmicsClaw Skill Guide — SC Filter
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-filter]
search_terms: [single-cell filtering, QC filtering, min genes, mitochondrial percent, tissue preset, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Filter

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-filter` skill. This is a living guide for threshold reasoning and
wrapper-specific caveats, not a claim that OmicsClaw already performs automatic
QC decision-making.

## Purpose

Use this guide when you need to decide:
- whether `sc-filter` should be run now or whether `sc-qc` is still needed first
- which filtering thresholds matter most in the current wrapper
- how to explain wrapper presets without pretending they are universal biology rules

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, inspect it
before running filtering.

Key properties to check:
- **QC metrics availability**:
  - `n_genes_by_counts`
  - `total_counts`
  - `pct_counts_mt`
- **Matrix state**:
  - current wrapper assumes count-like or QC-ready AnnData input
- **Biological context**:
  - blood, tumor, and solid tissues often justify different `%MT` tolerance
- **Filtering goal**:
  - remove low-quality cells only
  - remove extreme high-count / likely doublet-like cells
  - remove low-support genes

Important implementation notes in current OmicsClaw:
- the public workflow is `threshold_filtering`
- `tissue` is an OmicsClaw wrapper preset, not a Scanpy upstream parameter
- `min_genes`, `max_mt_percent`, and `min_cells` are the primary first-pass controls

## Step 2: Pick The Method Deliberately

Current OmicsClaw exposes one filtering workflow:

| Workflow | Best first use | Main caveat |
|----------|----------------|-------------|
| **threshold_filtering** | Standard QC thresholding after reviewing QC plots | Does not infer optimal cutoffs automatically |

## Step 3: Always Show A Parameter Summary Before Running

Before execution, summarize the real run in a short block, for example:

```text
About to run single-cell filtering
  Workflow: threshold_filtering
  Parameters: min_genes=200, max_mt_percent=20, min_cells=3
  Note: tissue presets are wrapper heuristics, not Scanpy-native parameters.
```

## Step 4: Method-Specific Tuning Rules

### Threshold Filtering

Tune in this order:
1. `min_genes`
2. `max_mt_percent`
3. `min_cells`
4. `max_genes` / `max_counts`
5. `tissue`

Guidance:
- start with `min_genes` and `max_mt_percent`; they usually control the largest low-quality tail
- use `min_cells` to remove ultra-rare genes after deciding cell retention
- use `max_genes` or `max_counts` when you specifically suspect high-count outliers or doublets
- use `tissue` only as a fast wrapper preset, then review whether its implied thresholds fit the biology

Important warnings:
- do not describe `tissue` as an official Scanpy argument
- do not imply this wrapper learns optimal cutoffs from the data
- do not treat `max_counts` and `max_genes` as universally mandatory first-pass knobs

## Step 5: What To Say After The Run

- If retention is unexpectedly low: revisit `min_genes` and `max_mt_percent` first.
- If obvious high-count outliers remain: consider adding `max_counts` or a dedicated doublet step.
- If users ask why genes disappeared: explain `min_cells` separately from cell filtering.
- If the preset felt too aggressive: say the issue is the wrapper heuristic, not necessarily the dataset quality.

## Step 6: Explain Outputs Using Method-Correct Language

When summarizing results:
- describe `filtered.h5ad` as the threshold-filtered AnnData
- describe `tables/filter_stats.csv` as the exact filtering audit trail
- describe `report.md` as the narrative summary of retained cells and genes
- describe the reproducibility bundle as the replayable command plus environment snapshot

## Official References

- https://scanpy.readthedocs.io/en/stable/api/scanpy.pp.filter_cells.html
- https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.filter_genes.html
- https://scanpy.readthedocs.io/en/stable/api/scanpy.pp.calculate_qc_metrics.html

