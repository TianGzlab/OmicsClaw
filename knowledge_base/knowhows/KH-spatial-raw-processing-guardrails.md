---
doc_id: spatial-raw-processing-guardrails
title: Spatial Raw Processing Guardrails
doc_type: knowhow
critical_rule: MUST verify that the request is truly sequencing-level spatial FASTQ processing with barcode-coordinate metadata, and MUST route matrix-level inputs to spatial-preprocess instead
domains: [spatial]
related_skills: [spatial-raw-processing, spatial-raw-fastq-processing, spatial-st-pipeline]
phases: [before_run, on_warning, after_run]
search_terms: [spatial raw processing, st_pipeline, spatial fastq, barcode coordinates, ids file, visium fastq, slide-seq fastq, spatial transcriptomics upstream, 空间原始FASTQ, 上游处理, 条形码坐标]
priority: 1.0
---

# Spatial Raw Processing Guardrails

- **Confirm the level of input first**: this skill is for sequencing-level spatial assays with FASTQ files. If the user already has `.h5ad`, Space Ranger matrices, or Xenium-style outputs, route to `spatial-preprocess` instead.
- **Require the real upstream contract**: explain that `--ids`, `--ref-map`, and `--ref-annotation` (unless `--transcriptome`) are not optional convenience metadata; they are core upstream requirements.
- **Do not overclaim platform support**: `platform` is a reporting label. It does not switch the upstream algorithm, and it should not be described as if OmicsClaw implements separate raw-processing methods for Visium, Slide-seq, or other barcode-coordinate assays.
- **State the handoff before execution**: tell the user that the output of this skill is `raw_counts.h5ad`, and that the canonical next step is `spatial-preprocess` for QC, normalization, embedding, and clustering.
- **Be explicit about low barcode recovery troubleshooting**: when barcode recovery or detected spots are low, point first to the IDs file format, `demultiplexing_mismatches`, `demultiplexing_kmer`, and UMI-layout assumptions.
- **Preserve upstream provenance**: keep `upstream/st_pipeline/` intact and describe it as the authoritative audit trail for the raw sequencing run.
- **For detailed tuning and edge cases**: see `knowledge_base/skill-guides/spatial/spatial-raw-processing.md`.
