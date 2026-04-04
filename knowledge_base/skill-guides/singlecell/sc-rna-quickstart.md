---
doc_id: skill-guide-sc-rna-quickstart
title: OmicsClaw Skill Guide — scRNA Quick Start
doc_type: method-reference
domains: [singlecell]
related_skills:
  - sc-fastq-qc
  - sc-count
  - sc-standardize-input
  - sc-qc
  - sc-preprocessing
  - sc-clustering
  - sc-batch-integration
  - sc-doublet-detection
  - sc-velocity-prep
  - sc-velocity
search_terms: [scRNA quick start, single-cell beginner workflow, FASTQ to h5ad, novice guide, 单细胞新手流程]
priority: 0.95
---

# OmicsClaw Skill Guide — scRNA Quick Start

**Status**: beginner-oriented workflow guide for users who do not already know
which single-cell skill to run first.

## Who This Is For

Use this guide when the user says something like:

- “我只有单细胞 FASTQ，下一步该做什么？”
- “我不懂单细胞流程，帮我一步一步跑”
- “我有 10x 数据，应该先 QC 还是先转 h5ad？”

This guide is intentionally opinionated and focuses on the current mainstream
OmicsClaw scRNA path.

## The Default Route

For a normal 10x scRNA project, the recommended path is:

1. `sc-fastq-qc`
2. `sc-count`
3. `sc-qc`
4. `sc-preprocessing`
5. optional branch:
   - `sc-doublet-detection` before interpretation if doublets are a concern
6. optional branch:
   - `sc-batch-integration` if there are multiple batches / donors / libraries
7. `sc-clustering`
8. downstream analysis such as:
   - `sc-cell-annotation`
   - `sc-de`
   - `sc-pseudotime`

If the user wants RNA velocity, insert:

1. `sc-velocity-prep`
2. `sc-velocity`

after preprocessing or after a suitable preprocessed object already exists.

## Start Here: What Does The User Actually Have?

### Case 1: The user has raw FASTQ files

This is the most common beginner starting point.

Recommended route:

1. run `sc-fastq-qc`
2. if quality is acceptable, run `sc-count`
3. pass the resulting `processed.h5ad` into `sc-qc`
4. then run `sc-preprocessing`
5. if doublets matter, run `sc-doublet-detection`
6. if multiple batches exist, run `sc-batch-integration`
7. then run `sc-clustering`

If the user explicitly wants:

- **Cell Ranger or STARsolo**: use `sc-count`
- **SimpleAF / Alevin-fry or kb-python**: still use `sc-count`, but switch `--method`

### Case 2: The user already has Cell Ranger or STARsolo output

Do **not** ask them to rerun FASTQ processing.

Recommended route:

1. import with `sc-count`
2. continue with `sc-qc`
3. continue with `sc-preprocessing`
4. then either `sc-batch-integration` or directly `sc-clustering`

### Case 3: The user already has an external `.h5ad`

Recommended route:

1. run `sc-standardize-input`
2. then `sc-qc`
3. then `sc-preprocessing`
4. then either `sc-batch-integration` or directly `sc-clustering`

This is the safest way to avoid hidden count-vs-normalized matrix problems.

### Case 4: The user wants RNA velocity

Ask whether they already have:

- a loom file
- a Cell Ranger BAM
- or STARsolo Velocyto output

Recommended route:

1. `sc-velocity-prep`
2. `sc-velocity`

Do **not** send users directly to `sc-velocity` if `spliced` and `unspliced`
layers do not already exist.

## Which Counting Skill Should A Beginner Choose?

### The safe default: `sc-count`

Use `sc-count` when:

- the user is on a mainstream 10x path
- they want Cell Ranger
- they want STARsolo
- they already have Cell Ranger or STARsolo outputs

### Advanced counting methods inside `sc-count`

If a user explicitly wants pseudoalignment, keep them on `sc-count` and switch:

- `--method simpleaf`
- `--method kb_python`

For a beginner who says nothing special, `sc-count --method cellranger` is the
more natural first default.

## Where Should A Beginner Put References?

If the user does not want to keep typing long absolute paths, recommend this
layout:

```text
resources/singlecell/references/
├── cellranger/
├── starsolo/
├── simpleaf/
├── kb/
├── whitelists/
└── gtf/
```

Then explain the rule in simple words:

- if there is only one obvious reference in the right directory, OmicsClaw can auto-detect it
- if there are multiple versions, the user should pass `--reference`, `--t2g`, `--gtf`, or `--whitelist` explicitly
- Cell Ranger references come from 10x official reference releases
- STARsolo usually reuses the same FASTA / GTF plus a STAR-built genome directory
- `sc-velocity-prep --method velocyto` usually reuses the same `genes.gtf` as the counting reference

## A Beginner-Friendly Command Sequence

### Standard 10x FASTQ route

```bash
oc run sc-fastq-qc --input fastqs/ --output output/sc_fastq_qc
oc run sc-count --input fastqs/ --method cellranger --reference /path/to/refdata-gex-GRCh38-2020-A --output output/sc_count
oc run sc-qc --input output/sc_count/processed.h5ad --output output/sc_qc
oc run sc-preprocessing --input output/sc_count/processed.h5ad --output output/sc_preprocessing
oc run sc-clustering --input output/sc_preprocessing/processed.h5ad --output output/sc_clustering
```

### Existing `.h5ad` route

```bash
oc run sc-standardize-input --input data.h5ad --output output/sc_standardize
oc run sc-qc --input output/sc_standardize/processed.h5ad --output output/sc_qc
oc run sc-preprocessing --input output/sc_standardize/processed.h5ad --output output/sc_preprocessing
oc run sc-clustering --input output/sc_preprocessing/processed.h5ad --output output/sc_clustering
```

### Velocity route

```bash
oc run sc-velocity-prep --input sample_count/ --method velocyto --gtf genes.gtf --output output/sc_velocity_prep
oc run sc-velocity --input output/sc_velocity_prep/velocity_input.h5ad --output output/sc_velocity
```

## The Main User Mistakes To Prevent

### Mistake 1: Jumping straight from FASTQ to clustering

Correct route:

- FASTQ QC
- counting
- QC
- base preprocessing
- clustering

### Mistake 2: Treating any `.h5ad` as ready for downstream analysis

Correct route:

- standardize first when provenance is unclear

### Mistake 3: Running `sc-velocity` on an ordinary count matrix

Correct route:

- prepare velocity layers first with `sc-velocity-prep`

## Simple Decision Rule For Routing

If the user only says:

- “10x FASTQ”
- “single-cell FASTQ”
- “raw single-cell data”

route them to:

- `sc-fastq-qc`, then `sc-count`

If they say:

- “Cell Ranger output”
- “STARsolo output”

route them to:

- `sc-count`

If they say:

- “Alevin-fry”
- “simpleaf”
- “kb-python”

route them to:

- `sc-count` with the corresponding `--method`

If they say:

- “velocity”
- “loom”
- “spliced/unspliced”

route them to:

- `sc-velocity-prep`

If they say:

- “CITE-seq”
- “ADT”
- “HTO”
- “cellranger multi”

then explain that this is outside the current mainline scRNA workflow and
should be handled in a future dedicated single-cell multi-omics path.
