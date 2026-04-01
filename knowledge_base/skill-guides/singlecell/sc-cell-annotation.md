---
doc_id: skill-guide-sc-cell-annotation
title: OmicsClaw Skill Guide — SC Cell Annotation
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-cell-annotation, sc-annotate]
search_terms: [single-cell annotation, CellTypist, SingleR, scmap, marker-based annotation, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Cell Annotation

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-cell-annotation` skill. This is a wrapper guide for method choice and
reference/model reasoning, not a claim that all upstream annotation features
are already exposed.

## Purpose

Use this guide when you need to decide:
- whether marker-based or reference/model-based annotation is the better first pass
- which parameters matter first in the current wrapper
- how to explain current fallback behavior honestly

## Step 1: Inspect The Data First

Key properties to check:
- **Cluster labels**:
  - `markers` depends on a sensible `cluster_key`
- **Reference / model availability**:
  - CellTypist needs a real model choice
  - reference-style paths need a trustworthy reference concept
- **Expression state**:
  - the wrapper expects preprocessed data

Important implementation notes in current OmicsClaw:
- implemented methods are `markers` and `celltypist`
- `singler` and `scmap` exist as compatibility method names but may fall back in the current wrapper
- `model` is the key user-facing CellTypist selector

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **markers** | Fast baseline when clusters are already interpretable | `cluster_key` | Quality is limited by upstream clustering and marker quality |
| **celltypist** | Best first automated model-based label transfer | `model` | Wrapper does not expose the full CellTypist tuning surface |
| **singler** | Compatibility label for reference-style annotation | `reference` | Current wrapper may fall back instead of running a full native bridge |
| **scmap** | Compatibility label for reference-style annotation | `reference` | Current wrapper may fall back instead of running a full native bridge |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run cell annotation
  Method: celltypist
  Parameters: model=Immune_All_Low
  Note: reference-style methods are exposed, but some R-side paths may currently fall back.
```

## Step 4: Method-Specific Tuning Rules

### Marker-Based

Tune in this order:
1. `cluster_key`

Guidance:
- use marker-based mode only when clusters already look biologically coherent

### CellTypist

Tune in this order:
1. `model`

Guidance:
- choose the smallest model that matches the biology before trying bigger generic atlases

Important warnings:
- do not expose `majority_voting`, `mode`, or other CellTypist internals as current public OmicsClaw parameters

### SingleR / scmap compatibility paths

Tune in this order:
1. `reference`

Important warnings:
- do not promise a full native SingleR / scmap wrapper if the current code path falls back
- explain fallback behavior explicitly when it occurs

## Step 5: What To Say After The Run

- If one label dominates everything: question reference/model mismatch before trusting the labels.
- If marker-based labels look noisy: question cluster quality first.
- If users ask why `singler`/`scmap` output resembles marker-based results: explain the current fallback behavior directly.

## Step 6: Explain Outputs Using Method-Correct Language

- describe `cell_type` as the standardized label column
- describe `annotation_method` as the actual wrapper method used
- describe confidence only when the chosen backend truly produced one

## Official References

- https://celltypist.readthedocs.io/en/latest/celltypist.annotate.html
- https://celltypist.readthedocs.io/en/latest/notebook/celltypist_tutorial.html
- https://github.com/Teichlab/celltypist
- https://bioconductor.org/packages/release/bioc/vignettes/SingleR/inst/doc/SingleR.html

