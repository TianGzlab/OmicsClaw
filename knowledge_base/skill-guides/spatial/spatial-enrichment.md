---
doc_id: skill-guide-spatial-enrichment
title: OmicsClaw Skill Guide — Spatial Enrichment
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-enrichment, enrichment]
search_terms: [spatial enrichment, pathway enrichment, gene set enrichment, enrichr, gsea, ssgsea, GO, Reactome, hallmark]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Enrichment

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-enrichment` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:

- whether ORA-style `enrichr`, preranked `gsea`, or group-level `ssgsea` is the
  right first pass
- how to explain gene-set source selection and fallback behavior
- which parameters matter first for the chosen enrichment method

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:

- **Grouping labels**: `obs[groupby]` must exist and contain biologically
  meaningful groups.
- **Expression representation**: `adata.X` should be log-normalized or otherwise
  suitable for Scanpy marker ranking and group-level scoring.
- **Question type**:
  - pathway interpretation of thresholded markers: `enrichr`
  - pathway interpretation of the full ranked list: `gsea`
  - group-level pathway score profiles: `ssgsea`
- **Gene-set source**:
  - local, deterministic first pass: `source=omicsclaw_core`
  - custom local library: `gene_set_file`
  - broader library key when external resolution is acceptable: `GO_*`,
    `Reactome_Pathways`, `MSigDB_Hallmark`, etc.

Important implementation notes in current OmicsClaw:

- `enrichr` first computes Scanpy markers and then runs ORA on positive markers.
- `gsea` also depends on the Scanpy marker table but keeps the full ranked list.
- `ssgsea` currently runs on **group-level mean expression profiles**, not on
  every spot independently.
- If the requested external library cannot be resolved, OmicsClaw falls back to
  a local signature library and records that in `library_mode`.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **Enrichr** | Fast biological interpretation of positive marker genes | `source=omicsclaw_core`, `de_method=wilcoxon`, `enrichr_padj_cutoff=0.05`, `enrichr_log2fc_cutoff=1.0`, `enrichr_max_genes=200` | Depends strongly on the marker thresholding step |
| **GSEA** | Detect subtle coordinated pathway shifts using the full ranked list | `de_method=wilcoxon`, `gsea_ranking_metric=auto`, `gsea_min_size=15`, `gsea_max_size=500`, `gsea_permutation_num=100`, `gsea_weight=1.0` | More computationally involved and more sensitive to ranking choices |
| **ssGSEA** | Compare group-level pathway score profiles rather than term-level p-values | `source=omicsclaw_core`, `ssgsea_sample_norm_method=rank`, `ssgsea_correl_norm_type=rank`, `ssgsea_min_size=15`, `ssgsea_max_size=500`, `ssgsea_weight=0.25` | Current wrapper is group-level mean-profile scoring, not per-spot scoring |

Practical default decision order:

1. If the user says "what pathways explain these marker genes", start with
   **Enrichr**.
2. If the user says "use the whole ranked gene list" or wants subtle pathway
   shifts, use **GSEA**.
3. If the user wants pathway scores per group, use **ssGSEA**.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial enrichment
  Method: GSEA
  Grouping: leiden
  Gene-set source: MSigDB_Hallmark
  Marker ranking: de_method=wilcoxon, de_corr_method=benjamini-hochberg
  Parameters: gsea_ranking_metric=auto, gsea_min_size=15, gsea_max_size=500, gsea_permutation_num=100
```

## Step 4: Method-Specific Tuning Rules

### Enrichr

Tune in this order:

1. `source` / `gene_set_file`
2. `de_method`
3. `de_corr_method`
4. `enrichr_padj_cutoff`
5. `enrichr_log2fc_cutoff`
6. `enrichr_max_genes`

Guidance:

- Start with `source=omicsclaw_core` for a deterministic local-first pass.
- Switch to `gene_set_file` when the user already has a curated local library.
- Use `GO_*`, `Reactome_Pathways`, or `MSigDB_Hallmark` only when the user wants
  that specific library and accepts external resolution.
- Keep `de_method=wilcoxon` as the first pass.
- Keep `enrichr_padj_cutoff=0.05` and `enrichr_log2fc_cutoff=1.0` unless the
  marker list is clearly too sparse or too broad.

Important warnings:

- ORA results are only as good as the upstream marker selection.
- Do not describe ORA overlap counts as equivalent to ranked-list enrichment.

### GSEA

Tune in this order:

1. `source` / `gene_set_file`
2. `de_method`
3. `de_corr_method`
4. `gsea_ranking_metric`
5. `gsea_min_size`
6. `gsea_max_size`
7. `gsea_permutation_num`
8. `gsea_weight`

Guidance:

- Start with `gsea_ranking_metric=auto`; OmicsClaw prefers `scores`, then
  `logfoldchanges`.
- Keep `gsea_min_size=15` and `gsea_max_size=500` for a first pass.
- Use `gsea_permutation_num=100` as the default interactive compromise; raise it
  when the user wants a heavier run.
- Keep `gsea_weight=1.0` unless the user explicitly wants a different weighting
  behavior.

Important warnings:

- If the chosen ranking metric changes, the biological interpretation may also
  change.
- Negative NES means the gene set is shifted toward the bottom of the ranked
  list for that group.

### ssGSEA

Tune in this order:

1. `source` / `gene_set_file`
2. `ssgsea_sample_norm_method`
3. `ssgsea_correl_norm_type`
4. `ssgsea_min_size`
5. `ssgsea_max_size`
6. `ssgsea_weight`

Guidance:

- Keep `ssgsea_sample_norm_method=rank` and `ssgsea_correl_norm_type=rank` for a
  first pass.
- Only use `log`, `log_rank`, `zscore`, or `symrank` when there is a clear
  reason to change the score geometry.
- Keep `ssgsea_weight=0.25` for the initial run.
- Explain clearly that current OmicsClaw ssGSEA is **group-level**.

Important warnings:

- Do not present projected group-level ssGSEA spatial maps as spot-level
  independent statistics.
- ssGSEA scores are comparative scores, not automatically adjusted p-values.

## Step 5: Gene-Set Source Rules

Use this decision order:

1. If the user wants a stable, local-first run, start with `omicsclaw_core`.
2. If the user provides a local gene-set library, use `gene_set_file`.
3. If the user explicitly asks for GO / Reactome / MSigDB and external
   resolution is acceptable, use the requested `source`.
4. If external resolution fails, say so explicitly and note the fallback
   library mode.

## Step 6: What To Say After The Run

- If many groups have no ORA hits: mention marker thresholds may be too strict
  or the chosen gene-set library may have low overlap with the dataset.
- If GSEA returns many significant pathways with modest NES: mention that ranked
  enrichment can detect coordinated but subtle shifts.
- If ssGSEA scores separate groups clearly but p-values are absent: explain that
  the output is a score profile rather than a standard significance table.
- If the library mode is a fallback: say so explicitly before interpreting the
  pathways as if they came from the requested external source.

## Step 7: Use The Visualization Layers Deliberately

Current OmicsClaw `spatial-enrichment` separates visualization into two layers:

- **Python standard gallery**:
  - canonical analysis output
  - emitted under `figures/` with `figures/manifest.json`
  - should be the default artifact used in interactive analysis and routine
    reporting
- **R customization layer**:
  - optional refinement layer
  - should consume `figure_data/*.csv`
  - should not rerun ORA, preranked GSEA, or ssGSEA just to restyle figures

Practical rule:

1. Use the Python gallery to confirm the science and the narrative structure.
2. Use the R layer only when the user explicitly wants publication styling,
   panel composition, or deeper aesthetic control.
3. If an R script needs extra inputs, export them from Python first instead of
   embedding scientific recomputation inside the plotting layer.

## Step 8: Explain Results Using Method-Correct Language

When summarizing results to the user:

- For **Enrichr**, refer to the output as ORA-style pathway enrichment on
  positive markers.
- For **GSEA**, refer to the output as preranked enrichment with NES-based
  interpretation.
- For **ssGSEA**, refer to the output as group-level pathway scoring.

Do **not** flatten all three outputs into a generic "pathway enrichment p-value
table" explanation. In current OmicsClaw they answer different questions.
