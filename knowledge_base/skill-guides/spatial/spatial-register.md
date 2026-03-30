---
doc_id: skill-guide-spatial-register
title: OmicsClaw Skill Guide — Spatial Register
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-registration, spatial-register, register]
search_terms: [spatial registration, slice alignment, PASTE, STalign, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Register

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-register` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:
- whether PASTE or STalign is the right registration backend
- which parameters matter first in the current OmicsClaw wrapper
- how to explain aligned coordinates without pretending both methods solve the same problem

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:
- **Slice labels**:
  - does a real `obs` column identify slices?
  - if multiple candidates exist, which one is biologically correct?
- **Slice count**:
  - 2 slices allows either PASTE or STalign
  - 3 or more slices currently points strongly toward PASTE in the wrapper
- **Spatial coordinates**:
  - registration requires spatial coordinates
- **Shared gene space**:
  - PASTE uses shared genes directly
  - STalign expression mode also relies on shared genes
- **Biological expectation**:
  - if the user wants smoother diffeomorphic warping of one slice onto another, STalign is more appropriate
  - if the user wants expression-aware alignment across multiple slices, PASTE is more appropriate

Important implementation notes in current OmicsClaw:
- The wrapper now requires a real slice-label column instead of silently fabricating one.
- PASTE aligns each non-reference slice directly to the chosen reference using `pairwise_align`.
- Current PASTE wrapper now exposes public `alpha`, `dissimilarity`, and `use_gpu`.
- Current STalign wrapper exposes public `a` and `niter`, while `stalign_image_size` and `use_expression` are wrapper-level controls around rasterization and signal preparation.
- STalign remains pairwise-only in the current wrapper.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **PASTE** | Default choice for 3 or more slices, or for expression-aware reference-based alignment | `paste_alpha=0.1`, `paste_dissimilarity=kl` | Current wrapper aligns each source slice to a reference rather than building a more elaborate stacked consensus |
| **STalign** | Pairwise registration when smooth spatial deformation is the main goal | `stalign_a=500`, `stalign_niter=2000`, `use_expression=false` first | Exactly 2 slices only in the current wrapper |

Practical default decision order:
1. If the dataset has 3 or more slices, start with **PASTE**.
2. If the dataset has exactly 2 slices and the user wants a smooth warping story, consider **STalign**.
3. If the user mainly wants expression-aware slice matching rather than image-like deformation, stay with **PASTE**.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial registration
  Method: PASTE
  Slice key: slice
  Reference slice: slice_1
  Parameters: paste_alpha=0.1, paste_dissimilarity=kl, paste_use_gpu=false
  Note: This is a 4-slice dataset, so PASTE is the more appropriate current OmicsClaw wrapper choice than STalign.
```

## Step 4: Method-Specific Tuning Rules

### PASTE

Tune in this order:
1. `reference_slice`
2. `paste_alpha`
3. `paste_dissimilarity`
4. `paste_use_gpu`

Guidance:
- Choose a biologically sensible and well-behaved reference slice first.
- Start with `paste_alpha=0.1`.
- Increase `paste_alpha` when spatial distance should matter more strongly relative to expression matching.
- Decrease `paste_alpha` when expression similarity should dominate more strongly.
- Start with `paste_dissimilarity=kl`.
- Only change dissimilarity when the user has a clear reason to prefer a different expression-distance behavior.
- Use `paste_use_gpu` only when the environment supports it and runtime is the real bottleneck.

Important warning:
- `paste_alpha` and `paste_dissimilarity` are public method controls; `reference_slice` is a workflow choice that often matters even more than the numeric tuning.

### STalign

Tune in this order:
1. `reference_slice`
2. `stalign_a`
3. `stalign_niter`
4. `use_expression`
5. `stalign_image_size`

Guidance:
- Choose the fixed target slice first.
- Start with `stalign_a=500`.
- Increase `stalign_a` for smoother, less flexible warps.
- Decrease `stalign_a` when a more flexible deformation is needed.
- Start with `stalign_niter=2000`.
- Increase it when the warp appears underfit and runtime is acceptable.
- Keep `use_expression=false` first if the user mainly cares about morphology-like coordinate alignment.
- Turn on `use_expression` when transcriptomic signal should contribute to the registration image.
- Treat `stalign_image_size` as a wrapper-level rasterization fidelity / runtime tradeoff.

Important warning:
- In the current wrapper, `use_expression` is not a raw upstream STalign switch; it controls whether OmicsClaw constructs a PC1-derived intensity image before calling LDDMM.

## Step 5: Slice-Key Rules

- If multiple candidate columns exist, do not guess silently. Tell the user which slice column you plan to use.
- If no real slice-label column exists, do not proceed with a fabricated one.
- If the user says "align sample A to sample B," confirm which `obs` column maps to those labels.

## Step 6: What To Say After The Run

- If PASTE succeeds but alignment still looks poor: suggest revisiting the reference slice choice and `paste_alpha`.
- If STalign fails on a multi-slice dataset: explain that the current wrapper is pairwise-only and recommend PASTE.
- If STalign with `use_expression` uses few common genes: mention that the wrapper may have fallen back to a uniform signal.
- If no slice column can be detected: explain that this is a metadata problem, not a registration-tuning problem.
- If only one slice is present: say that registration is not meaningful yet because there is no second slice to align.

## Step 7: Explain Results Using Method-Correct Language

When summarizing results:
- For **PASTE**, describe the output as reference-based optimal-transport alignment using expression plus spatial distance.
- For **STalign**, describe the output as pairwise diffeomorphic alignment through LDDMM.
- Refer to `spatial_aligned` as the aligned coordinate space exported by OmicsClaw.
- Describe `registration_metrics.csv` as per-slice alignment scores when PASTE produces them.

Do **not** collapse PASTE and STalign into a generic "registration score"
story. In the current wrapper, they rely on different assumptions and expose
different meaningful parameters.
