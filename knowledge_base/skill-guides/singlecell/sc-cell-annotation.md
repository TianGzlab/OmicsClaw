---
doc_id: skill-guide-sc-cell-annotation
title: OmicsClaw Skill Guide — SC Cell Annotation
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-cell-annotation, sc-annotate]
search_terms: [single-cell annotation, CellTypist, SingleR, marker-based annotation, tuning]
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
  - marker scoring, CellTypist, SingleR, and scmap should read log-normalized expression
  - when `adata.raw` exists and matches the current cells/genes, treat it as the preferred source for annotation backends
- **Input provenance**:
  - if the object is external and count-vs-normalized state is unclear, recommend `sc-standardize-input` first

Important implementation notes in current OmicsClaw:
- implemented methods are `markers`, `celltypist`, `singler`, and `scmap`
- `singler` and `scmap` are available via the shared R bridge when the required R packages are installed
- `model` is the key user-facing CellTypist selector
- if CellTypist input validation or model execution fails, the wrapper may fall back to `markers` and records both requested and actual methods

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **markers** | Fast baseline when clusters are already interpretable | `cluster_key` | Quality is limited by upstream clustering and marker quality; use log-normalized expression rather than counts |
| **celltypist** | Best first automated model-based label transfer | `model` | Wrapper does not expose the full CellTypist tuning surface |
| **singler** | Reference-based annotation through SingleR | `reference` | Requires an R environment with SingleR and celldex |
| **scmap** | Cluster-level projection against a reference atlas | `reference` | Requires the R `scmap` stack and is only as good as the reference clusters |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run cell annotation
  Method: celltypist
  Parameters: model=Immune_All_Low
  Note: reference-style paths read log-normalized expression, preferably from adata.raw.
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
- if the current matrix still looks count-like, do not present CellTypist as if it can run natively without either preprocessing first or explicitly accepting marker fallback

### SingleR

Tune in this order:
1. `reference`

Important warnings:
- ensure the requested reference is available in the current R environment
- be explicit that this path depends on Bioconductor packages outside the Python environment
- make the user confirm the reference choice instead of blindly running the default HPCA atlas on unknown biology

### scmap

Tune in this order:
1. `reference`

Important warnings:
- use scmap for atlas projection, not as a substitute for marker reasoning when clusters are badly defined
- keep the explanation clear that scmap is reference-driven and depends on the R bridge stack

## Step 5: What To Say After The Run

- If one label dominates everything: question reference/model mismatch before trusting the labels.
- If marker-based labels look noisy: question cluster quality first.
- If CellTypist fell back: explain why the fallback happened and make it explicit that the final labels came from `markers`, not CellTypist.
- If SingleR cannot run: explain which R packages are missing instead of pretending marker mode is equivalent.
- If scmap and SingleR disagree: report the disagreement and revisit the reference choice before forcing a single label story.

## Step 6: Explain Outputs Using Method-Correct Language

- describe `cell_type` as the standardized label column
- describe `annotation_method` as the actual wrapper method used
- when a fallback happened, describe the requested and executed methods separately
- describe confidence only when the chosen backend truly produced one

## Official References

- https://celltypist.readthedocs.io/en/latest/celltypist.annotate.html
- https://celltypist.readthedocs.io/en/latest/notebook/celltypist_tutorial.html
- https://github.com/Teichlab/celltypist
- https://bioconductor.org/packages/release/bioc/vignettes/SingleR/inst/doc/SingleR.html
- https://bioconductor.org/packages/release/bioc/html/scmap.html
