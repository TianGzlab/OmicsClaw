---
doc_id: skill-guide-sc-velocity-prep
title: OmicsClaw Skill Guide — SC Velocity Prep
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-velocity-prep]
search_terms: [RNA velocity prep, velocyto, STARsolo Velocyto, loom, spliced unspliced, velocity-ready AnnData]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Velocity Prep

**Status**: implementation-aligned guide for the current
`sc-velocity-prep` wrapper. It explains how OmicsClaw creates velocity-ready
layers before the downstream `sc-velocity` modeling step.

## Purpose

Use this guide when you need to decide:

- whether the source is Cell Ranger + BAM, STARsolo Velocyto output, loom, or raw FASTQ
- whether to merge velocity layers into an existing base `h5ad`
- how to explain the difference between “preparing layers” and “running velocity inference”

## Step 1: Inspect The Source Type First

There are four main upstream entry states.

### 1. Cell Ranger output directory

Best when the user has:

- `possorted_genome_bam.bam`
- filtered barcodes
- the matching gene annotation GTF

This maps to the `velocyto` path.

### 2. STARsolo Velocyto output

Best when the user already has:

- `spliced.mtx`
- `unspliced.mtx`
- `barcodes.tsv`
- `features.tsv`

This maps to the import side of the `starsolo` path.

### 3. Loom file

Best when a previous velocyto step is already done. This is usually the easiest
import case.

### 4. Raw FASTQ only

This is supported only through the current narrow STARsolo velocity wrapper,
not through automatic Cell Ranger + velocyto orchestration.

## Step 2: Explain What This Skill Actually Does

Current OmicsClaw `sc-velocity-prep` does:

1. detect Cell Ranger, STARsolo, loom, or FASTQ input
2. run velocyto or STARsolo when needed
3. import `spliced`, `unspliced`, and optional `ambiguous` layers
4. optionally merge these layers into an existing base `h5ad`
5. save `processed.h5ad` and keep `velocity_input.h5ad` as a compatibility alias

Current OmicsClaw `sc-velocity-prep` does **not**:

1. compute velocity vectors
2. choose stochastic versus dynamical mode
3. generate latent time
4. prove that the prepared layers will produce biologically meaningful velocity

Those belong to `sc-velocity`.

## Step 3: Pick The Method Deliberately

| Method | Best first use | Why choose it | Main caveat |
|--------|----------------|---------------|-------------|
| **velocyto** | Cell Ranger outputs with BAM already available | official loom-oriented route and easiest hand-off to scVelo | needs GTF and filtered barcodes |
| **starsolo** | Existing STARsolo Velocyto matrices or open FASTQ-based velocity prep | keeps everything in one STAR-family toolchain | wrapper is intentionally scoped to mainstream 10x-style geometry |

## Step 4: Use Official Input Constraints Honestly

### velocyto

Official velocyto docs assume:

- BAM sorted by genomic position
- corrected cell barcode tags in the BAM
- corrected UMI tags in the BAM
- a GTF compatible with the annotation used upstream

The docs also warn that running without a filtered barcode set is not
recommended because runtime and memory can become very large.

### scVelo

Official scVelo docs are explicit that the key input is:

- spliced counts
- unspliced counts

and that these live in `adata.layers`. The docs also explicitly support
merging a loom object into an existing AnnData object.

### STARsolo

Official STARsolo docs show that:

- `--soloFeatures Gene Velocyto` adds spliced / unspliced / ambiguous quantification
- this requires `Gene` features to be included
- `EmptyDrops_CR` is the Cell Ranger-like cell-calling option

That is exactly why OmicsClaw’s current STARsolo velocity path stays close to
`Gene + Velocyto` rather than exposing the full STARsolo option surface.

## Step 5: Explain Merge Behavior Carefully

If `--base-h5ad` is used:

- OmicsClaw aligns by shared cells and shared genes
- the merge is an intersection, not a union
- if barcodes differ only by suffix conventions such as `-1`, OmicsClaw tries a lightweight normalization pass

Do not promise that every upstream object can be reconciled automatically.

## Step 5.5: If The User Is Missing GTF Or STAR References, Guide Them Gently

Recommended project-local layout:

- `resources/singlecell/references/gtf/`
- `resources/singlecell/references/starsolo/`
- `resources/singlecell/references/whitelists/`

### BAM + velocyto path

Tell the user:

- the safest GTF is the one that matches the reference used upstream
- if they ran Cell Ranger, the easiest choice is usually the same `genes.gtf` from that reference package
- place it under `resources/singlecell/references/gtf/`, or pass it directly with `--gtf`

Beginner-friendly example:

```bash
mkdir -p resources/singlecell/references/gtf
cp /path/to/refdata-gex-GRCh38-2020-A/genes/genes.gtf resources/singlecell/references/gtf/
oc run sc-velocity-prep --input sample_count/ --method velocyto --gtf resources/singlecell/references/gtf/genes.gtf --output output/sc_velocity_prep
```

### FASTQ + STARsolo velocity path

Tell the user:

- build or reuse a STAR genome directory under `resources/singlecell/references/starsolo/`
- download the matching barcode whitelist under `resources/singlecell/references/whitelists/`
- pass both explicitly if there are multiple versions on disk

Beginner-friendly example:

```bash
mkdir -p resources/singlecell/references/whitelists
curl -L -o resources/singlecell/references/whitelists/3M-february-2018.txt.gz https://github.com/10XGenomics/cellranger/raw/master/lib/python/cellranger/barcodes/3M-february-2018.txt.gz
gunzip -f resources/singlecell/references/whitelists/3M-february-2018.txt.gz
```

## Step 6: Know The Biological Caveat

Successful preparation does **not** imply successful biology.

Even with correct layers:

- some datasets have very low unspliced fractions
- some protocols or tissues produce weak velocity signal
- some prepared objects will still lead to noisy or unstable downstream arrows

The right language is:

- “velocity-ready object prepared successfully”

not:

- “RNA velocity is scientifically validated”

## Step 7: Good Pre-Run Summary

```text
About to prepare RNA-velocity input
  Method: velocyto
  Source: Cell Ranger output directory
  Required upstream inputs: BAM, filtered barcodes, GTF
  Optional merge: base h5ad
  Output hand-off: processed.h5ad for sc-velocity
```

## Step 8: Explain The Handoff Correctly

After the run:

- `processed.h5ad` is the main file to give to `sc-velocity`
- `velocity_input.h5ad` is kept as a compatibility alias
- the result is about layer preparation, not velocity inference
- preserved artifacts such as loom path or STARsolo directory still matter for auditability

## Official References

- velocyto CLI guide: https://velocyto.org/velocyto.py/tutorial/cli.html
- scVelo getting started: https://scvelo.readthedocs.io/en/stable/getting_started.html
- scVelo velocity basics: https://scvelo.readthedocs.io/en/stable/VelocityBasics.html
- STARsolo official docs: https://github.com/alexdobin/STAR/blob/master/docs/STARsolo.md
- Cell Ranger reference release notes: https://www.10xgenomics.com/support/software/cell-ranger/latest/release-notes/cr-reference-release-notes
