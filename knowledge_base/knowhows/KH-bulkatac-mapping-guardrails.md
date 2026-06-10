---
doc_id: bulkatac-mapping-guardrails
title: Bulk ATAC Mapping Guardrails
doc_type: knowhow
critical_rule: MUST verify a valid bulkatac-preprocessing result.json is chained in, explain the aligner and reference resolution before running, and never claim the BAMs are Tn5-shifted — the +4/-5 offset is deliberately left to downstream tools
domains: [epigenomics]
related_skills: [bulkatac-mapping]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ATAC mapping, ATAC alignment, Bowtie2, BWA, ENCODE BAM filter, NRF PBC, TSS enrichment, ATAC比对]
priority: 1.0
---

# Bulk ATAC Mapping Guardrails

- **Inspect first**: confirm a Step-1 `preprocessing/result.json` is resolvable — via `--prev-result` (alias `--input`) or sibling-detected next to `--output`; the run hard-fails if neither resolves. There is no `--demo` flag.
- **Do not overclaim scope**: this skill aligns + filters + dedups BAMs and computes post-alignment QC only — it does NOT call peaks, FRiP, or IDR (`bulkatac-peak-calling`), and does NOT do differential accessibility.
- **Explain the run before execution**: state the effective `--aligner` (bowtie2 default or bwa), `--genome`, `--threads`, whether `--downsample` is on (OFF by default — opt in only when depth is uneven), and that MAPQ ≥ 30 is hard-coded in the ENCODE filter (not a CLI flag).
- **Use wrapper-correct language**: `--bwa-index` and `--bowtie2-index` are mutually exclusive and must match `--aligner`; with no index supplied the reference + ENCODE blacklist are auto-downloaded (~3-5 GB) into a sibling `reference_<genome>/` dir.
- **Preserve the contract**: successful runs emit `report.md`, `result.json`, `mapping_summary.csv`, `bam/<sample>.dedup.bam` (+`.bai`), `bigwig/<sample>.rpgc.bw`, `qc_after_mapping/` (TSS + fragment-length), and `reproducibility/` under `--output`.
- **Interpret outputs correctly**: BAMs are NOT Tn5-shifted by design — downstream tools (TOBIAS `ATACorrect`, MACS2 `--shift`/`--extsize`) apply the offset; NRF/PBC1/PBC2 and TSS scores carry ENCODE tier labels that vary by `--cell-type`.
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkatac-mapping.md`.
