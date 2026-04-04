---
doc_id: skill-guide-sc-count
title: OmicsClaw Skill Guide — SC Count
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-count]
search_terms: [single-cell counting, Cell Ranger, STARsolo, feature-barcode matrix, 10x, counting guide]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Count

**Status**: implementation-aligned guide for the current `sc-count` wrapper.
It explains how OmicsClaw covers the mainstream first-wave counting workflow
without pretending to support every single-cell protocol already.

## Purpose

Use this guide when you need to decide:

- whether to import an existing count output or run a backend from FASTQ
- whether Cell Ranger or STARsolo is the better first choice
- what the current wrapper really supports and what is still intentionally deferred

## Step 1: Decide Whether This Is An Import Or A Real Backend Run

First inspect the input path.

### Import path

If the user already has:

- a Cell Ranger directory containing `outs/filtered_feature_bc_matrix*`
- or a STARsolo directory containing `Solo.out/Gene/filtered`

then the correct action is usually to import and standardize the filtered matrix.
Do not require a reference directory for this path.

### Backend run path

If the user only has FASTQ files, then:

- Cell Ranger requires a compatible transcriptome reference and FASTQ folder
- STARsolo requires a STAR genome directory and an explicit supported chemistry / whitelist contract

## Step 2: Choose The Backend Deliberately

| Backend | Best first use | Why choose it | Main caveat |
|--------|----------------|---------------|-------------|
| **Cell Ranger** | Standard 10x Chromium GEX workflow | Official 10x path, stable outputs, easiest downstream interoperability | Closed-source / external binary dependency |
| **STARsolo** | Open alternative for mainstream 10x-style droplet runs | Official STAR extension, fast, Cell Ranger-like matrix outputs | Wrapper currently limited to mainstream 10x geometry |

Current wrapper decision rule:

- default to **Cell Ranger** when the user is on a standard 10x path and has the tool installed
- use **STARsolo** when the user explicitly wants the open route or already has STARsolo outputs

## Step 2.5: If The User Is Missing Reference Files, Tell Them Exactly What To Do

Recommended project-local layout:

- `resources/singlecell/references/cellranger/`
- `resources/singlecell/references/starsolo/`
- `resources/singlecell/references/simpleaf/`
- `resources/singlecell/references/kb/`
- `resources/singlecell/references/whitelists/`

OmicsClaw can auto-detect a reference only when there is exactly one obvious
candidate in the matching directory. Otherwise the user should pass an explicit
path such as `--reference`, `--t2g`, or `--whitelist`.

### Cell Ranger reference

Tell the user:

- go to the official 10x Cell Ranger reference release notes and download a matching transcriptome reference
- unpack it under `resources/singlecell/references/cellranger/`
- or pass the unpacked directory directly with `--reference`

Beginner-friendly example:

```bash
mkdir -p resources/singlecell/references/cellranger
tar -xf refdata-gex-GRCh38-2020-A.tar.gz -C resources/singlecell/references/cellranger
oc run sc-count --input fastqs/ --method cellranger --reference resources/singlecell/references/cellranger/refdata-gex-GRCh38-2020-A --output output/sc_count
```

### STARsolo reference + whitelist

Tell the user:

- easiest path is to reuse the same FASTA / GTF as the 10x reference, then build a STAR genome directory
- place that STAR genome directory under `resources/singlecell/references/starsolo/`
- place the barcode whitelist under `resources/singlecell/references/whitelists/`

Beginner-friendly example:

```bash
mkdir -p resources/singlecell/references/starsolo/GRCh38_star
STAR --runMode genomeGenerate --runThreadN 16 --genomeDir resources/singlecell/references/starsolo/GRCh38_star --genomeFastaFiles /path/to/genome.fa --sjdbGTFfile /path/to/genes.gtf

mkdir -p resources/singlecell/references/whitelists
curl -L -o resources/singlecell/references/whitelists/3M-february-2018.txt.gz https://github.com/10XGenomics/cellranger/raw/master/lib/python/cellranger/barcodes/3M-february-2018.txt.gz
gunzip -f resources/singlecell/references/whitelists/3M-february-2018.txt.gz
```

### simpleaf index

Tell the user:

- if they already have a simpleaf index, move or symlink it into `resources/singlecell/references/simpleaf/`
- otherwise build one according to the official simpleaf indexing workflow, then pass it with `--reference`

### kb-python index + t2g

Tell the user:

- if they already have a kallisto index and `t2g`, move them into `resources/singlecell/references/kb/`
- otherwise follow the official kb reference-building workflow first

Beginner-friendly example:

```bash
mkdir -p resources/singlecell/references/kb
mv kallisto.idx resources/singlecell/references/kb/
mv t2g.txt resources/singlecell/references/kb/
```

## Step 3: Know The Stable Outputs

### Cell Ranger

The official Cell Ranger count docs describe a stable output contract including:

- `filtered_feature_bc_matrix/`
- `filtered_feature_bc_matrix.h5`
- `raw_feature_bc_matrix/`
- `raw_feature_bc_matrix.h5`
- `metrics_summary.csv`
- `molecule_info.h5`
- `possorted_genome_bam.bam`
- `web_summary.html`

These are exactly the artifacts OmicsClaw should preserve because:

- raw `.h5` is useful for ambient correction
- BAM is useful for velocity preparation
- filtered matrix is the cleanest hand-off to the AnnData-first downstream stack

### STARsolo

The official STARsolo docs describe:

- Cell Ranger-like matrix outputs under `Solo.out/`
- `Gene/raw` and `Gene/filtered` outputs
- `Summary.csv`
- optional BAM output

OmicsClaw’s current wrapper imports the filtered matrix and preserves the run
directory for later reuse.

## Step 4: Explain Current Scope Boundaries Honestly

Current OmicsClaw `sc-count` does:

1. detect FASTQ samples or existing backend outputs
2. run the selected counting backend when needed
3. import the filtered matrix
4. standardize it into `processed.h5ad`
5. preserve backend artifact paths in the result object

Current OmicsClaw `sc-count` does **not** yet promise:

1. `cellranger multi`
2. CITE-seq / HTO / CRISPR-specific wrapper logic
3. Smart-seq / Smart-seq3 counting
4. Drop-seq / inDrops / Parse / custom barcode geometry
5. BCL demultiplexing as a first-class skill

Advanced backends are available inside the same skill:

- `cellranger`
- `starsolo`
- `simpleaf`
- `kb_python`

Important note:

- 10x has already deprecated `cellranger mkfastq` in current releases and recommends BCL Convert for generating FASTQs. That means OmicsClaw’s first-wave upstream focus should stay on **FASTQ onward**, not on trying to own BCL demultiplexing immediately.

## Step 5: Handle STARsolo Carefully

The current wrapper intentionally narrows STARsolo to the most stable part of the official docs:

- `CB_UMI_Simple`
- supported 10x chemistry geometry
- `EmptyDrops_CR`
- `Gene` output for matrix counting

Do not imply that the wrapper already exposes:

- full custom complex barcode specifications
- SmartSeq mode
- arbitrary protocol strings
- the entire STARsolo parameter surface

## Step 6: Good Pre-Run Summary

```text
About to run single-cell counting
  Method: cellranger
  Input: FASTQ directory
  Sample: PBMC_1
  Output hand-off: processed.h5ad
  Preserved artifacts: filtered matrix, raw matrix when available, backend BAM/logs
```

## Step 7: Explain The Handoff Correctly

After the run:

- `processed.h5ad` is the main downstream hand-off to OmicsClaw
- but backend artifacts are still important

Typical next steps:

- `sc-qc`
- `sc-preprocessing`
- `sc-ambient-removal` when raw Cell Ranger outputs are available
- `sc-velocity-prep` when BAM or STARsolo Velocyto outputs are needed

## Official References

- Cell Ranger count pipeline: https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/running-pipelines/cr-gex-count
- Cell Ranger reference release notes: https://www.10xgenomics.com/support/software/cell-ranger/latest/release-notes/cr-reference-release-notes
- Cell Ranger gene expression outputs: https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/outputs/cr-outputs-gex-overview
- FASTQ generation / BCL Convert note: https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/inputs/cr-direct-demultiplexing
- Cell Ranger FASTQ selection: https://www.10xgenomics.com/support/software/cell-ranger/9.0/analysis/inputs/cr-specifying-fastqs
- STARsolo official docs: https://github.com/alexdobin/STAR/blob/master/docs/STARsolo.md
- simpleaf quant docs: https://simpleaf.readthedocs.io/en/latest/quant-command.html
- kb-python count docs: https://kb-python.readthedocs.io/en/stable/autoapi/kb_python/count/
- kb-python repository: https://github.com/pachterlab/kb_python
- nf-core/scrnaseq usage: https://nf-co.re/scrnaseq/dev/docs/usage
