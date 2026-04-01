---
doc_id: skill-guide-sc-de
title: OmicsClaw Skill Guide — SC Differential Expression
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-de]
search_terms: [single-cell differential expression, Wilcoxon, DESeq2 pseudobulk, groupby, replicates, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Differential Expression

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-de` skill. This guide emphasizes the difference between exploratory
single-cell marker ranking and replicate-aware pseudobulk inference.

## Purpose

Use this guide when you need to decide:
- whether the user wants exploratory marker ranking or formal condition DE
- which method is the best first pass
- which parameters matter first in the current wrapper

## Step 1: Inspect The Design First

Key properties to check:
- **Comparison target**:
  - cluster markers vs condition comparison
- **Grouping variable**:
  - `groupby` must reflect the intended biological comparison
- **Replicates**:
  - `deseq2_r` only makes sense if replicate/sample structure exists
- **Cell-type restriction**:
  - pseudobulk paths often need a meaningful `celltype_key`

Important implementation notes in current OmicsClaw:
- `wilcoxon` and `t-test` are Scanpy exploratory paths
- `mast` is currently a compatibility label, not a full native MAST implementation
- `deseq2_r` is the wrapper’s replicate-aware pseudobulk path

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **wilcoxon** | Safest first-pass marker or group ranking | `groupby`, `n_top_genes` | Exploratory, not replicate-aware |
| **t-test** | Parametric alternative for simple group ranking | `groupby`, `n_top_genes` | Still exploratory |
| **mast** | Compatibility label only | `groupby`, `n_top_genes` | Current wrapper does not expose a full native MAST backend |
| **deseq2_r** | Best formal path for replicate-aware condition DE | `groupby`, `group1`, `group2`, `sample_key`, `celltype_key` | Needs true replicate structure |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run single-cell differential expression
  Method: deseq2_r
  Parameters: groupby=condition, group1=treated, group2=control, sample_key=sample_id, celltype_key=cell_type
  Note: this is a pseudobulk replicate-aware path, not simple per-cell ranking.
```

## Step 4: Method-Specific Tuning Rules

### Exploratory Scanpy Paths

Tune in this order:
1. `groupby`
2. `method`
3. `n_top_genes`
4. `group1` / `group2`

Guidance:
- use these when the goal is fast ranking, not formal replicate-aware inference

### DESeq2 pseudobulk

Tune in this order:
1. `groupby`
2. `group1` / `group2`
3. `sample_key`
4. `celltype_key`

Guidance:
- choose this path only when the user truly has replicate-level samples
- `sample_key` and `celltype_key` are as important as the statistical method itself

Important warnings:
- do not expose a free-form DESeq2 design formula as if the wrapper supports it
- do not oversell `mast` as a full current backend

## Step 5: What To Say After The Run

- If users want cluster markers: recommend keeping the explanation in exploratory language.
- If users want treatment-vs-control claims without replicates: say the design is weak before discussing p-values.
- If pseudobulk results look odd: revisit `sample_key` and `celltype_key` before blaming DESeq2.

## Step 6: Explain Outputs Using Method-Correct Language

- describe Scanpy results as ranked marker-style DE outputs
- describe DESeq2 results as pseudobulk replicate-aware inference
- describe `de_full.csv` as the full result table and `markers_top.csv` as the condensed export

## Official References

- https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html
- https://bioconductor.org/packages/release/bioc/vignettes/DESeq2/inst/doc/DESeq2.html
