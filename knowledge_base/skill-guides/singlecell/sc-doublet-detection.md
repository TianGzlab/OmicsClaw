---
doc_id: skill-guide-sc-doublet-detection
title: OmicsClaw Skill Guide — SC Doublet Detection
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-doublet-detection, sc-doublet]
search_terms: [doublet detection, Scrublet, DoubletFinder, scDblFinder, expected doublet rate, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Doublet Detection

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-doublet-detection` skill. This guide explains the current wrapper surface,
not every backend-specific parameter described upstream.

## Purpose

Use this guide when you need to decide:
- whether doublet detection should be run before clustering / annotation / DE
- which backend is the most appropriate first pass
- how to explain expected doublet rate and thresholding honestly

## Step 1: Inspect The Data First

Key properties to check:
- **Capture type**:
  - droplet-based datasets are the primary use case
- **Load / multiplexing context**:
  - expected doublet burden depends on loading and sample design
- **Current analysis stage**:
  - doublet labeling is usually more useful before final annotation
- **Input provenance**:
  - if the object came from outside OmicsClaw, recommend `sc-standardize-input` first, then confirm the matrix used here is still raw count-like

Important implementation notes in current OmicsClaw:
- the wrapper exposes `scrublet`, `doubletfinder`, and `scdblfinder`
- `threshold` only affects the Scrublet path
- `doubletfinder` may fall back to `scdblfinder` if the R runtime fails
- the wrapper annotates doublets; it does not automatically drop them

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **scrublet** | Fast Python-native first pass | `expected_doublet_rate`, optional `threshold` | Threshold override only applies here |
| **doubletfinder** | When an R-based Seurat-style path is explicitly desired | `expected_doublet_rate` | Current wrapper does not expose the full DoubletFinder tuning stack and may fall back to `scdblfinder` on runtime failure |
| **scdblfinder** | Strong R/Bioconductor baseline with a simpler public surface | `expected_doublet_rate` | Wrapper hides many advanced scDblFinder options |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run doublet detection
  Method: scrublet
  Parameters: expected_doublet_rate=0.06, threshold=auto
  Note: threshold override is only implemented for the Scrublet path.
```

## Step 4: Method-Specific Tuning Rules

### Shared first-pass rule

Tune in this order:
1. `expected_doublet_rate`
2. `threshold` (Scrublet only)

Guidance:
- `expected_doublet_rate` is the main shared scientific prior in the current wrapper
- only use manual `threshold` when Scrublet’s automatic separation is clearly unsatisfactory
- if the user selected an R method but also supplied a Scrublet-only `threshold`, stop and ask which behavior they actually want

Important warnings:
- do not promise DoubletFinder `pK`, `pN`, or `nExp`; the wrapper does not expose them
- do not promise scDblFinder sample-level / cluster-level fine controls; the wrapper does not expose them

## Step 5: What To Say After The Run

- If many doublets are called: mention loading burden or sample complexity, not just “bad quality”.
- If very few are called: mention the assumed expected rate and whether the threshold was conservative.
- If `doubletfinder` fell back: explain both the requested and executed methods rather than presenting the result as native DoubletFinder output.
- If users ask whether cells were removed: state clearly that the wrapper labels but does not auto-delete.

## Step 6: Explain Outputs Using Method-Correct Language

- describe `doublet_score` as backend-specific evidence, not a universal probability
- describe `predicted_doublet` as the wrapper’s boolean call
- describe `doublet_classification` as the human-readable summary column

## Official References

- https://github.com/swolock/scrublet
- https://github.com/chris-mcginnis-ucsf/DoubletFinder/blob/master/README.md
- https://bioconductor.org/packages/release/bioc/vignettes/scDblFinder/inst/doc/scDblFinder.html
- https://github.com/plger/scDblFinder/blob/devel/README.md
