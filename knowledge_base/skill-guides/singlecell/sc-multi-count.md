---
doc_id: skill-guide-sc-multi-count
title: OmicsClaw Skill Guide — SC Multi Count
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-multi-count]
search_terms: [cellranger multi, CITE-seq, HTO, antibody capture, multimodal handoff]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Multi Count

**Status**: implementation-aligned guide for the current `sc-multi-count`
wrapper. It explains how OmicsClaw preserves Cell Ranger multi outputs while
still producing an RNA-only handoff for the current downstream stack.

## Purpose

Use this guide when you need to decide:

- whether to import an existing `cellranger multi` run or execute one from config
- how to explain the difference between the preserved multimodal object and the RNA handoff
- what the current wrapper does not yet promise for multimodal downstream analysis

## Step 1: Inspect The Input Type

### Existing multi outputs

If the user already has a completed run with:

- `outs/filtered_feature_bc_matrix.h5`
- `outs/per_sample_outs/`
- `qc_report.html`

then the usual correct move is to import and standardize, not rerun.

### Config CSV

If the input is a `cellranger multi` config CSV, the wrapper can execute the
backend when `cellranger` is installed.

## Step 2: Explain The Two-Object Contract

This skill writes:

1. `multimodal_standardized_input.h5ad`
2. `rna_standardized_input.h5ad`

The first preserves:

- Gene Expression
- Antibody Capture / ADT
- Multiplexing Capture / HTO

when those feature types exist.

The second is intentionally RNA-only and is the safer object for existing
single-cell downstream skills in OmicsClaw.

## Step 3: Use Current Scope Language Correctly

Current OmicsClaw `sc-multi-count` does:

1. import or run `cellranger multi`
2. preserve multimodal feature types
3. derive an RNA-only downstream handoff
4. export modality summary tables and figures

Current OmicsClaw `sc-multi-count` does **not** yet promise:

1. multimodal WNN-style integration
2. CLR normalization of ADT
3. joint RNA+ADT clustering
4. HTO demultiplexing logic beyond preserving backend outputs
5. CITE-seq-specific downstream annotation logic

## Step 4: Handle `per_sample_outs/` Carefully

For multiplexed runs:

- top-level outputs may summarize all assigned cells
- `per_sample_outs/<sample>/` contains sample-specific filtered matrices

If the user wants one biological sample, choose `--sample`. If they want the
global assigned-cell matrix, omit it and explain that choice.

## Step 5: What To Say After The Run

Good post-run language:

- “The multimodal object was preserved.”
- “The RNA-only handoff is the correct input for current RNA downstream skills.”
- “ADT / HTO features remain available for future multimodal workflows.”

Avoid saying:

- “OmicsClaw now fully supports CITE-seq downstream analysis.”

That would not be true yet.

## Official References

- Cell Ranger outputs overview: https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/outputs/cr-outputs-overview
- Cell Ranger multi multiplex outputs: https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/outputs/cr-3p-outputs-cellplex
- Cell Ranger release notes around multi outputs: https://www.10xgenomics.com/support/software/cell-ranger/latest/release-notes/cr-release-notes
