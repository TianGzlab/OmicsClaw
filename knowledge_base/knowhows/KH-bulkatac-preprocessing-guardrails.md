---
doc_id: bulkatac-preprocessing-guardrails
title: Bulk ATAC Preprocessing Guardrails
doc_type: knowhow
critical_rule: MUST confirm the input is a sample sheet of raw bulk ATAC FASTQs, explain the resolved trimmer and trim cutoffs before running, and never claim alignment, post-alignment QC, or peak calling — this skill only validates the sheet and trims adapters
domains: [epigenomics]
related_skills: [bulkatac-preprocessing, bulkatac-preprocess]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ATAC preprocessing, FASTQ adapter trimming, fastp, Trim Galore, FastQC, Nextera adapter, ATAC预处理, 染色质可及性]
priority: 1.0
---

# Bulk ATAC Preprocessing Guardrails

- **Inspect first**: confirm the `--input` is a TSV/CSV sample sheet with `sample, condition, replicate, R1 [, R2]` — single-end vs paired-end is auto-detected from the `R2` column, not configurable.
- **Do not overclaim scope**: this skill only validates the sheet, runs optional FastQC, and trims Nextera adapters — it does NOT align, dedup, compute NRF/PBC or TSS QC (`bulkatac-mapping`), call peaks (`bulkatac-peak-calling`), or do DA.
- **Explain the run before execution**: state the effective `--tool` (fastp default, or trim_galore), `--quality` (default Q20), `--min-length` (default 36 bp, ENCODE minimum), `--adapter` (Nextera `CTGTCTCTTATACACATCT`), and whether FastQC runs (`--no-fastqc` to skip).
- **Use wrapper-correct language**: `--genome` is metadata only — it is silently coerced to `sacCer3` under `--demo` and is never used for trimming; it is just stashed for `bulkatac-mapping`. `--tool auto` resolves post-run to the actual trimmer.
- **Preserve the contract**: successful runs emit `report.md`, `result.json`, `fastq_trimmed/` (trimmed FASTQs + `trimmed_summary.csv`), `reproducibility/`, and `README.md` directly under `--output` (no nested subdir).
- **Interpret outputs correctly**: per-sample trim stats live in `fastq_trimmed/trimmed_summary.csv` and `result.json["preprocessing"]` — there is no `tables/` directory; trimmed-FASTQ paths are carried per-sample in `result.json`, not as CSV columns.
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkatac-preprocessing.md`.
