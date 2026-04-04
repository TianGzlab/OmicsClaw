---
doc_id: skill-guide-sc-fastq-qc
title: OmicsClaw Skill Guide — SC FASTQ QC
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-fastq-qc]
search_terms: [single-cell FASTQ QC, FastQC, MultiQC, Q30, adapter contamination, read quality]
priority: 0.8
---

# OmicsClaw Skill Guide — SC FASTQ QC

**Status**: implementation-aligned guide for the current `sc-fastq-qc`
wrapper. It explains how OmicsClaw combines mainstream FastQC / MultiQC usage
with a stable local fallback summary.

## Purpose

Use this guide when you need to decide:

- whether the user really wants raw-read QC rather than counting
- whether the input layout is one sample or multiple sample groups
- how to interpret the current wrapper output without pretending it trims or repairs reads

## Step 1: Inspect The Input Layout First

Before running, inspect:

- **Input type**:
  - one FASTQ file plus explicit `--read2`
  - or a directory containing one or more paired FASTQ groups
- **Sample grouping**:
  - if more than one sample stem exists, require `--sample`
- **Paired-end structure**:
  - confirm that paired files really match the same sample and lane pattern
- **Scope of the question**:
  - if the user wants matrix generation, cell calling, or barcode-rank plots, the right next skill is `sc-count`, not `sc-fastq-qc`

## Step 2: Explain The Current Wrapper Correctly

Current OmicsClaw `sc-fastq-qc` does:

1. discover FASTQ samples from one file or a directory
2. run FastQC when the binary is available
3. run MultiQC on the FastQC outputs when the binary is available
4. always compute a lightweight Python fallback summary from sampled reads
5. write figures, tables, figure-data CSVs, report, result JSON, README, and reproducibility files

Current OmicsClaw `sc-fastq-qc` does **not**:

1. trim reads
2. remove adapters
3. rewrite FASTQs
4. demultiplex BCL into FASTQ
5. generate count matrices or AnnData

## Step 3: Interpret The Main Metrics Carefully

### `q20_pct` and `q30_pct`

- Use them as broad read-quality summaries.
- Do not claim that one fixed Q30 cutoff decides whether scRNA-seq is usable.

### GC percentage

- Read it as a descriptive summary, not an automatic pass/fail.
- Strong shifts may suggest unusual composition, but interpretation still depends on library design.

### Adapter-seed percentage

- Treat it as a lightweight contamination hint in the current Python fallback.
- If FastQC is available, prefer the official FastQC HTML report for adapter interpretation.

### Per-base quality curves

- Look for end-of-read decay or abrupt quality collapse.
- Do not expect R1 and R2 to be identical for every single-cell library.

Important note:

- For mainstream 10x droplet workflows, read structure is asymmetric. Barcode/UMI and cDNA reads play different roles, so quality profiles can differ even when the run is technically acceptable.

## Step 4: Explain FastQC And MultiQC Honestly

- **FastQC** is a read-level QC reporter. It provides HTML reports and module summaries for raw sequencing files.
- **MultiQC** does not perform QC by itself. It recursively scans tool outputs that already exist and summarizes them into one HTML report and one `multiqc_data/` directory.

This matters because users often assume that running MultiQC “does QC”. It does not. It aggregates QC outputs.

## Step 5: Good Pre-Run Summary

```text
About to run scRNA FASTQ QC
  Input type: FASTQ directory
  Selected sample: PBMC_1
  External tools: FastQC and MultiQC if available
  Stable fallback: sampled Python summary will always be written
  Scope: diagnostics only; no reads will be modified
```

## Step 6: What To Say After The Run

- If FastQC and MultiQC were available: point users to those artifacts first for tool-native interpretation.
- If they were unavailable: explain that the OmicsClaw fallback summary is still valid for a lightweight local screen, but it is not a full FastQC replacement.
- If quality looks acceptable:
  - recommend `sc-count` for the normal next step
  - mention that advanced users can switch `sc-count --method` to `simpleaf` or `kb_python` if they explicitly want those backends
- If quality looks problematic: say the next step is to fix the sequencing / preprocessing decision upstream, not to run downstream clustering anyway.

## Output Interpretation

- `figures/fastq_q30_summary.png`: compact sample-level overview
- `figures/per_base_quality.png`: per-base mean quality curves
- `figures/fastq_file_quality.png`: file-level Q30, adapter, GC, and read-length relationships
- `tables/fastq_per_file_summary.csv`: one row per FASTQ file
- `tables/fastq_per_sample_summary.csv`: one row per logical sample
- `artifacts/fastqc/`: official FastQC outputs when installed
- `artifacts/multiqc/`: aggregated MultiQC report when installed

## Official References

- FastQC overview: https://www.bioinformatics.babraham.ac.uk/projects/
- MultiQC overview: https://docs.seqera.io/multiqc/
- Running MultiQC: https://docs.seqera.io/multiqc/getting_started/running_multiqc
- MultiQC quick start: https://docs.seqera.io/multiqc/getting_started/quick_start
