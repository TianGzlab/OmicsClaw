---
doc_id: skill-guide-sc-qc
title: OmicsClaw Skill Guide — SC QC
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-qc]
search_terms: [scRNA QC, single-cell QC, mitochondrial percentage, ribosomal percentage, count depth, genes per cell, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC QC

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-qc` skill. This is a living wrapper guide for execution reasoning and
output interpretation. It is not a claim that OmicsClaw already implements all
possible single-cell QC frameworks.

## Purpose

Use this guide when you need to decide:

- whether `sc-qc` is the right skill before filtering
- how to explain the current `qc_metrics` implementation honestly
- how to interpret the standard QC gallery before moving to `sc-preprocessing`

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in the conversation, inspect it
before running QC.

Key properties to check:

- **Matrix type**:
  - current `sc-qc` works best when a raw count-like matrix exists in `layers["counts"]`, aligned `adata.raw`, or `adata.X`
  - if `adata.X` already looks log-normalized or scaled, say that explicitly and let the wrapper fall back to counts when available
- **Input provenance**:
  - if counts or gene symbols come from an external object with unclear provenance, recommend `sc-standardize-input` first
- **Gene naming convention**:
  - `human` expects mitochondrial `MT-` and ribosomal `RP[SL]`
  - `mouse` expects mitochondrial `mt-` and ribosomal `Rp[sl]`
  - Ensembl-only IDs or custom symbols can weaken `%MT` and `%ribo` estimates
- **Dataset scale**:
  - very sparse data tends to show broader low-count tails
  - very large datasets may still be fine here because the skill only computes QC metrics and plots
- **Biological context**:
  - blood, tumor, immune, and metabolic tissues can imply different acceptable `%MT` ranges

Important implementation notes in current OmicsClaw:

- The current skill exposes one public method: `qc_metrics`.
- `--species` is the only public extra flag.
- Ribosomal percentage is always computed in the current wrapper.
- The skill writes QC annotations into a canonical downstream-ready `processed.h5ad` but does not remove any cells.
- The current wrapper now shares the same preflight style as other main scRNA skills: no raw count-like matrix should hard-stop the run; weaker gene-symbol matching should produce warnings rather than fake precision.
- Loader, preflight, and standardization now have separate roles: `smart_load` reads and records a basic contract, `preflight` decides what to tell the user, and `sc-standardize-input` is the explicit repair path when provenance is messy.
- The saved `processed.h5ad` is intentionally still a count-oriented object: `adata.X` is raw count-like, `adata.layers["counts"]` is the canonical raw layer, and `adata.raw` is a count-like snapshot. Normalized-expression workflows usually still need `sc-preprocessing` next.

## Step 2: Explain The Current Skill Correctly

Current OmicsClaw `sc-qc` does:

1. load data through the shared single-cell loader
2. detect mitochondrial and ribosomal genes from `--species`
3. calculate Scanpy QC metrics
4. add log-transformed helper metrics
5. render the standard OmicsClaw QC gallery through the shared single-cell `_lib/viz` layer
6. export tables, figure-data CSVs, report, result JSON, AnnData, README, and reproducibility files

Current OmicsClaw `sc-qc` does **not**:

1. choose filtering cutoffs automatically
2. apply cell filtering
3. apply gene filtering
4. run doublet detection
5. normalize or cluster the data

Do not describe the skill as if it already performs full QC decision-making.
It is a diagnostics and evidence-generation step.

## Step 3: Handle The Only Public Tuning Knob Properly

### `species`

Tune in this order:

1. `species`

Guidance:

- Use `human` when gene symbols follow uppercase human conventions such as `MT-ND1` and `RPL13`.
- Use `mouse` when gene symbols follow mixed-case mouse conventions such as `mt-Nd1` and `Rpl13`.
- If the dataset uses Ensembl IDs or custom renamed features, tell the user that mitochondrial and ribosomal tagging may be incomplete before the run.

Important warning:

- `species` is a wrapper-level control, but it materially changes QC percentages by controlling which genes are tagged as mitochondrial or ribosomal.

## Step 4: Show An Effective Run Summary Before Execution

Before execution, give a short explicit summary such as:

```text
About to run single-cell QC
  Method: qc_metrics
  Species: human
  Ribosomal percentage: enabled by default in current wrapper
  Scope: diagnostic only; no cells or genes will be filtered
```

This matters because users often hear "QC" and assume filtering is included.

## Step 5: Interpret The Gallery In Context

### `n_genes_by_counts`

- A low-complexity tail can suggest empty droplets or damaged cells.
- A very high-complexity tail can suggest doublets or merged barcodes.
- Do not reuse one universal cutoff across all tissues.

### `total_counts`

- Very low counts may indicate weak capture or low RNA content.
- Very high counts may suggest doublets or highly loaded droplets.
- Always interpret together with `n_genes_by_counts`.

### `pct_counts_mt`

- Elevated `%MT` often suggests stressed or dying cells.
- PBMC-like data often supports stricter thresholds.
- Solid tissues and tumors often need broader tolerance.
- Metabolically active tissues may show biologically elevated `%MT`.

### `pct_counts_ribo`

- High ribosomal fraction can reflect biology or technical dominance.
- Use it as supporting evidence, not as a standalone exclusion rule.

### Highest-expressed-gene panel

- Look for dominant contaminants or suspiciously overwhelming features.
- This panel is especially useful when one or two genes consume a large fraction of the library.

## Step 6: What To Say After The Run

- If `%MT` appears uniformly low but gene naming is nonstandard: warn that tagging may be incomplete.
- If the low-count tail is large: suggest reviewing cell-quality thresholds in `sc-preprocessing`.
- If the high-count/high-gene tail is obvious: suggest follow-up doublet analysis rather than immediately discarding cells blindly.
- If distributions differ strongly across known samples or batches: note that later batch-aware QC reasoning may be needed.
- Always restate that no filtering was applied by `sc-qc`.

## Step 7: Explain Outputs Correctly

When summarizing results:

- describe `processed.h5ad` as the canonical downstream-ready AnnData with standardized scRNA contract fields plus QC annotations, `layers["counts"]`, and `adata.raw`
- describe `figures/` as the standard Python gallery users should inspect first, including the barcode-rank curve and QC correlation heatmap
- describe `figure_data/` as the stable hand-off layer for downstream custom plotting, including future R-side styling
- describe `tables/qc_metrics_summary.csv` as the compact metric summary
- describe `tables/qc_metrics_per_cell.csv` as the per-cell export for threshold review or custom plots
- describe `result.json.data.params` as the replayable public CLI settings
- describe `result.json.data.effective_params` as the actual runtime configuration, including fixed wrapper behavior
- describe `result.json.data.visualization` as the structured gallery contract

Do **not** imply that the skill filtered cells successfully simply because it
produced QC plots. The correct next step is to decide thresholds or pass the
annotated object into a filtering/preprocessing skill.
