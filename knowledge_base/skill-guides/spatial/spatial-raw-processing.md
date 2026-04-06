---
doc_id: skill-guide-spatial-raw-processing
title: OmicsClaw Skill Guide — Spatial Raw Processing
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-raw-processing, spatial-raw-fastq-processing, spatial-st-pipeline]
search_terms: [spatial raw processing, st_pipeline, spatial fastq, barcode coordinates, ids file, visium fastq, slide-seq fastq, upstream spatial processing, raw spatial counts]
priority: 0.82
---

# OmicsClaw Skill Guide — Spatial Raw Processing

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-raw-processing` skill. This is an **upstream** wrapper around
`st_pipeline`, not a matrix-level preprocessing workflow.

## Purpose

Use this guide when you need to decide:
- whether the user should run `spatial-raw-processing` or `spatial-preprocess`
- which inputs are mandatory before starting a raw sequencing run
- which first-pass upstream parameters matter when barcode recovery or count yield looks poor
- how to explain the handoff from raw FASTQs to `raw_counts.h5ad`

## Step 1: Separate Sequencing-Level Inputs From Matrix-Level Inputs

Before anything else, classify the input correctly.

Use `spatial-raw-processing` when the user has:
- R1 / R2 FASTQ files from a barcode-based spatial assay
- a barcode-to-coordinate IDs file
- a STAR reference index
- a gene annotation file, or an upstream transcriptome-mode plan

Do **not** use `spatial-raw-processing` when the user already has:
- `.h5ad`
- Space Ranger matrix directories or `filtered_feature_bc_matrix*`
- Xenium-style exports
- matrix-like TSV/MTX outputs that are already post-alignment and post-counting

Those belong in `spatial-preprocess`.

## Step 2: Verify The Upstream Contract Explicitly

The current wrapper expects these inputs to be real and local:

| Requirement | Why it is needed |
|-------------|------------------|
| `read1`, `read2` | raw barcoded read pair |
| `ids` | barcode-to-coordinate mapping; must contain `BARCODE X Y` columns |
| `ref_map` | STAR genome index directory |
| `ref_annotation` | gene model for annotation unless `--transcriptome` is used |
| `exp_name` | optional, but the wrapper will infer or fill it for stable output naming |

Important implementation notes:
- The IDs file is part of the scientific contract, not just convenience metadata.
- The current wrapper validates the IDs structure before running upstream processing.
- The wrapper preserves zero-count barcodes from the IDs file so downstream coordinate-aware analyses remain possible.

## Step 3: Explain How OmicsClaw Finds `st_pipeline`

Current resolution order is:
1. `--stpipeline-repo <repo_root>` or `OMICSCLAW_ST_PIPELINE_REPO`
2. `st_pipeline_run` on `PATH`
3. installed Python package import (`python -m stpipeline.scripts.st_pipeline_run`)

Use this when the user asks whether they must edit `.env`.

Guidance:
- `.env` is **not** required if the user passes `--stpipeline-repo` explicitly.
- `.env` or shell environment variables are useful when they want a stable default checkout path.
- If none of the three resolution paths is valid, the skill should fail fast with an installation/path message rather than trying to improvise.

## Step 4: Pick Parameters In The Right Order

The current wrapper intentionally exposes only the first-pass knobs that matter most.

| Parameter group | Best first use | Strong starting point | Main caveat |
|-----------------|----------------|-----------------------|-------------|
| Core files | Always first | validate `ids`, `ref_map`, `ref_annotation` | Missing or wrong files dominate all downstream failures |
| `threads` | Runtime scaling | `4` | Throughput control, not a biology parameter |
| `compute_saturation` | Depth sufficiency checks | off unless the user wants saturation output | Adds runtime |
| Barcode demultiplexing | Low barcode recovery | `demultiplexing_mismatches=2`, `demultiplexing_kmer=6` | Aggressive mismatch settings can admit wrong barcode assignments |
| UMI controls | Kit-layout mismatch | upstream defaults | Only change when protocol docs justify it |
| `platform` | Reporting clarity | `visium` or user-supplied label | Does not change the upstream algorithm |

## Step 5: What To Say Before Running

Use a short concrete preview such as:

```text
About to run spatial raw processing
  Method: st_pipeline
  Inputs: FASTQ R1/R2 + ids/barcodes + STAR index + annotation
  Output object: raw_counts.h5ad
  Next OmicsClaw step: spatial-preprocess
  First-pass upstream knobs: threads=4, demultiplexing_mismatches=2, demultiplexing_kmer=6
```

This matters because users often assume raw-processing also performs normalization or clustering. It does not.

## Step 6: Edge Cases And Failure Modes

### Wrong input type

If the user provides `.h5ad`, Space Ranger outputs, or Xenium exports:
- say clearly that the input is already matrix-level
- route to `spatial-preprocess`
- do not claim that `st_pipeline` can consume those inputs directly

### Multiple FASTQ pairs in one directory

If more than one pair is found:
- require `--read1` and `--read2` explicitly
- do not guess which pair is correct

### Low barcode recovery or unexpectedly sparse output

Check in this order:
1. IDs file format and coordinate mapping
2. demultiplexing settings
3. UMI layout assumptions
4. upstream protocol compatibility with the default wrapper assumptions

### Transcriptome mode

If `--transcriptome` is used:
- explain that `ref_annotation` is no longer required by the wrapper
- be explicit that the gene tag is then taken from the transcriptome-mode path upstream

## Step 7: Explain Outputs Correctly

When summarizing results:
- describe `raw_counts.h5ad` as the canonical OmicsClaw handoff object
- describe `upstream/st_pipeline/` as the preserved upstream audit trail
- describe `tables/` as complete downstream-ready exports rather than ad hoc diagnostics
- describe `figure_data/` as publication-ready inputs for restyling, not a second scientific analysis layer

Do **not** say raw processing already completed preprocessing. The correct sequence is:
1. `spatial-raw-processing`
2. `spatial-preprocess`
3. downstream spatial analysis skills
