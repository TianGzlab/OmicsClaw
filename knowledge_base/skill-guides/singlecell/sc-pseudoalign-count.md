---
doc_id: skill-guide-sc-pseudoalign-count
title: OmicsClaw Skill Guide — SC Pseudoalign Count
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-pseudoalign-count]
search_terms: [simpleaf, alevin-fry, kb-python, pseudoalign count, 10x, count handoff]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Pseudoalign Count

**Status**: implementation-aligned guide for the current
`sc-pseudoalign-count` wrapper. It explains the pseudoalignment-based count
handoff path without claiming full chemistry coverage from upstream tools.

## Purpose

Use this guide when you need to decide:

- whether to import an existing pseudoalignment result or execute a backend from FASTQ
- whether `simpleaf` or `kb_python` is the better fit
- how to explain the current wrapper boundaries honestly

## Step 1: Decide Whether This Is An Import Or A Real Run

### Import path

If the user already has:

- an importable `h5ad`
- or a matrix output directory created by SimpleAF / Alevin-fry
- or a kb-python result directory with importable matrices

then import and standardize rather than rerunning the backend.

### Real run path

If the user only has FASTQ files:

- `simpleaf` needs an index and chemistry hint
- `kb_python` needs an index, `t2g`, and technology string

## Step 2: Pick The Backend Deliberately

| Backend | Best first use | Why choose it | Main caveat |
|--------|----------------|---------------|-------------|
| **simpleaf** | modern Alevin-fry path with direct AnnData export | convenient `--anndata-out` handoff | wrapper still narrowed to mainstream droplet chemistries |
| **kb_python** | kallisto|bustools-compatible alternative | familiar pseudoalignment workflow and official gene-count API | requires `t2g` and the wrapper does not expose the full upstream option surface |

## Step 3: Explain The Current Wrapper Correctly

Current OmicsClaw `sc-pseudoalign-count` does:

1. import or run a pseudoalignment backend
2. load the resulting counts
3. standardize them into `standardized_input.h5ad`
4. export count-summary tables and figures

Current OmicsClaw `sc-pseudoalign-count` does **not** yet promise:

1. all custom chemistry geometries
2. Smart-seq-specific pseudoalign support
3. feature-barcode-specific pseudoalignment downstream logic
4. the full backend tuning surface from SimpleAF or kb-python

## Step 4: Use Official Backend Notes Honestly

### simpleaf

The official docs make two points especially relevant to this wrapper:

- `quant` can start from reads with `--index --reads1 --reads2`
- `--anndata-out` can produce an AnnData object directly

That is why OmicsClaw uses the cleanest possible direct-handoff path here.

### kb-python

The official kb-python API docs show that counting depends on:

- index path
- transcript-to-gene map
- technology string

That is why `--t2g` is required for real kb-backed runs in OmicsClaw.

### nf-core

nf-core/scrnaseq is useful as a community reference because it still treats
Cell Ranger and STARsolo as the main first-wave aligners, while exposing
SimpleAF and kallisto-style alternatives. That matches OmicsClaw’s decision to
keep pseudoalignment as an alternative count path, not the only default.

## Step 5: Good Pre-Run Summary

```text
About to run pseudoalignment-based counting
  Method: simpleaf
  Input: FASTQ directory
  Chemistry: 10xv3
  Output hand-off: standardized_input.h5ad
  Scope: count generation only; no downstream QC or clustering yet
```

## Step 6: What To Say After The Run

- If the wrapper imported an existing `h5ad`, say that clearly.
- If the backend ran for real, preserve and mention the backend run directory.
- Point downstream users to `standardized_input.h5ad` as the main handoff.

## Official References

- simpleaf quant docs: https://simpleaf.readthedocs.io/en/latest/quant-command.html
- kb-python count API docs: https://kb-python.readthedocs.io/en/stable/autoapi/kb_python/count/
- nf-core/scrnaseq usage: https://nf-co.re/scrnaseq/dev/docs/usage
