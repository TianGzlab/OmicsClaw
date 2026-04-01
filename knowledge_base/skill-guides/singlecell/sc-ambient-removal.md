---
doc_id: skill-guide-sc-ambient-removal
title: OmicsClaw Skill Guide — SC Ambient Removal
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-ambient-removal]
search_terms: [ambient RNA, CellBender, SoupX, contamination fraction, raw h5, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Ambient Removal

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-ambient-removal` skill. This guide focuses on real wrapper behavior and
input requirements, not the full upstream CellBender or SoupX parameter space.

## Purpose

Use this guide when you need to decide:
- whether ambient removal is actually justified before downstream analysis
- whether the user has the inputs required for `cellbender` or `soupx`
- which parameters matter in the current wrapper

## Step 1: Inspect The Data First

Key properties to check:
- **Technology context**:
  - droplet-based data is the main use case
- **Input assets**:
  - raw 10x `.h5` for CellBender
  - paired raw / filtered 10x directories for SoupX
- **Current matrix state**:
  - the wrapper fallback uses the current expression matrix directly
- **Contamination evidence**:
  - marker leakage, ambient signatures, or strong background genes

Important implementation notes in current OmicsClaw:
- the wrapper exposes `simple`, `cellbender`, and `soupx`
- `simple` is an OmicsClaw fallback, not an official CellBender/SoupX equivalent
- `contamination` is a wrapper-side control for the `simple` path

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **simple** | Fast baseline when raw inputs for other tools are missing | `contamination=0.05` | Wrapper heuristic, not a full probabilistic model |
| **cellbender** | Best when a raw 10x `.h5` from CellRanger is available | `raw_h5`, `expected_cells` | Heavy model; processed `.h5ad` is rejected by the current wrapper |
| **soupx** | Best when raw and filtered 10x directories are available | `raw_matrix_dir`, `filtered_matrix_dir` | Current wrapper does not expose the full SoupX tuning surface |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run ambient RNA removal
  Method: cellbender
  Parameters: raw_h5=sample_raw.h5, expected_cells=10000
  Note: this wrapper exposes only the core input/prior knobs, not the full CellBender training API.
```

## Step 4: Method-Specific Tuning Rules

### Simple

Tune in this order:
1. `contamination`

Guidance:
- use it as a fallback when no better method inputs are available
- increase only if background contamination is clearly visible

### CellBender

Tune in this order:
1. `raw_h5`
2. `expected_cells`

Guidance:
- `raw_h5` is not optional for a real CellBender run
- the current wrapper expects the raw 10x `.h5` produced by CellRanger, not a postprocessed `.h5ad`
- `expected_cells` is the main public prior worth exposing in the current wrapper

Important warnings:
- do not promise low-level CellBender knobs such as latent-dimension or training internals
- do not write `total-droplets-included` as a current OmicsClaw public parameter

### SoupX

Tune in this order:
1. `raw_matrix_dir`
2. `filtered_matrix_dir`

Guidance:
- confirm both directories exist before claiming SoupX is available
- if those inputs are missing, explain the fallback explicitly

## Step 5: What To Say After The Run

- If counts drop only slightly: say contamination may have been mild.
- If correction is very strong: tell the user to sanity-check marker retention.
- If CellBender/SoupX could not run: explain the missing inputs rather than pretending the fallback is equivalent.

## Step 6: Explain Outputs Using Method-Correct Language

- describe `corrected.h5ad` as the corrected expression object
- describe the before/after count plots as wrapper diagnostics, not formal validation metrics
- describe `result.json.data.params` as the actual public settings used

## Official References

- https://cellbender.readthedocs.io/en/stable/usage
- https://cellbender.readthedocs.io/en/v0.2.2/help_and_reference/remove_background/index.html
- https://github.com/broadinstitute/CellBender/blob/master/docs/source/usage/index.rst
- https://github.com/constantAmateur/SoupX
