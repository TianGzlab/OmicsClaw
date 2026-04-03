---
doc_id: sc-fastq-qc-guardrails
title: Single-Cell FASTQ QC Guardrails
doc_type: knowhow
critical_rule: MUST explain that sc-fastq-qc is a diagnostic read-quality step and does not trim reads, demultiplex BCL, or generate count matrices
domains: [singlecell]
related_skills: [sc-fastq-qc]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell FASTQ QC, FastQC, MultiQC, read quality, Q30, adapter contamination, 单细胞 FASTQ 质控]
priority: 1.0
source_urls:
  - https://www.bioinformatics.babraham.ac.uk/projects/
  - https://docs.seqera.io/multiqc/
  - https://docs.seqera.io/multiqc/getting_started/running_multiqc
---

# Single-Cell FASTQ QC Guardrails

- **Explain scope honestly**: this skill assesses raw FASTQ quality; it does not trim adapters, repair reads, demultiplex BCL, or generate matrices / AnnData.
- **Inspect the input layout first**: confirm whether the user supplied one paired sample or a directory containing multiple sample groups; require `--sample` when the directory is ambiguous.
- **Treat FastQC and MultiQC as reporting layers**: MultiQC summarizes outputs from other tools and does not perform analysis itself; do not describe it as a QC algorithm.
- **Do not overinterpret FastQC warnings**: module flags are diagnostic cues, not automatic proof that a run is unusable.
- **Remember 10x read asymmetry**: for mainstream 10x libraries, barcode/UMI and cDNA reads have different roles, so R1 and R2 profiles need not look identical. This is an inference from the upstream protocol structure and should be explained carefully rather than treated as a universal rule for every chemistry.
- **Be explicit about the current wrapper fallback**: OmicsClaw tries FastQC and MultiQC when those binaries are installed, but it always writes its own sampled Python summary so the report remains stable in minimal environments.
- **Do not pretend this replaces counting QC**: if the user wants cell calling, barcode rank curves, or feature-barcode matrices, the next step is `sc-count`, not another read-level QC rerun.
- **For detailed operator guidance**: see `knowledge_base/skill-guides/singlecell/sc-fastq-qc.md`.
