---
doc_id: bulkchip-preprocessing-guardrails
title: Bulk ChIP Preprocessing Guardrails
doc_type: knowhow
critical_rule: MUST confirm the input is a sample sheet of raw bulk ChIP-seq FASTQs WITH matched input/IgG controls, explain the resolved trimmer and trim cutoffs before running, and never claim alignment, ChIP QC, or peak calling — this skill only validates the sheet (incl. ChIP/control pairing) and trims adapters
domains: [epigenomics]
related_skills: [bulkchip-preprocessing, bulkchip-preprocess]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ChIP preprocessing, ChIP-seq FASTQ adapter trimming, fastp, Trim Galore, FastQC, input control pairing, Illumina adapter, ChIP预处理]
priority: 1.0
---

# Bulk ChIP Preprocessing Guardrails

- **Implemented**: this skill runs for real (FastQC + fastp/Trim Galore) and has a working `--demo` (nf-core SPT5 ChIP-seq test set). It needs the `omicsclaw_bulkchip` conda env — `bash 0_setup_env_for_bulkchip.sh` first. (The downstream bulkchip skills are still scaffolds.)
- **Inspect first**: confirm `--input` is a TSV/CSV sample sheet with `sample, condition, replicate, R1 [, R2], control, antibody [, peak_mode]`. Every ChIP sample must reference an existing input/IgG control; single-end vs paired-end is auto-detected from `R2`.
- **Do not overclaim scope**: this skill only validates the sheet (incl. ChIP↔control pairing), runs optional FastQC, and trims adapters — it does NOT align, dedup, compute NRF/PBC or NSC/RSC (`bulkchip-mapping`), call peaks (`bulkchip-peak-calling`), or do differential binding.
- **Explain the run before execution**: state the effective `--tool` (fastp default, or trim_galore), `--quality` (default Q20), `--min-length` (default 20 bp; ENCODE processable 25 bp, recommended 50 bp), `--adapter` (Illumina universal `AGATCGGAAGAGC`, NOT the ATAC Nextera adapter), and whether FastQC runs.
- **Use wrapper-correct language**: `--genome` and `peak_mode` are metadata only — never used for trimming, just stashed for `bulkchip-mapping` / `bulkchip-peak-calling`. Controls are trimmed exactly like ChIP samples.
- **Preserve the contract**: successful runs emit `report.md`, `result.json` (carrying `sample_sheet` + `control_map`), `fastq_trimmed/` (+ `trimmed_summary.csv`), `reproducibility/`, `README.md` directly under `--output`.
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkchip-preprocessing.md`.
