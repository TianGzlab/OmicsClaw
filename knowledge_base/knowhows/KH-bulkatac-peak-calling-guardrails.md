---
doc_id: bulkatac-peak-calling-guardrails
title: Bulk ATAC Peak Calling Guardrails
doc_type: knowhow
critical_rule: MUST verify a valid bulkatac-mapping result.json is chained in, explain the MACS2 q-value and consensus overlap fraction before running, and never claim differential accessibility is performed — this skill stops at the consensus count matrix
domains: [epigenomics]
related_skills: [bulkatac-peak-calling]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ATAC peak calling, MACS2, narrowPeak, naive overlap consensus, featureCounts, FRiP, IDR, ATAC峰检测]
priority: 1.0
---

# Bulk ATAC Peak Calling Guardrails

- **Inspect first**: confirm a Step-2 `mapping/result.json` (with dedup BAMs) is resolvable — via `--prev-result` (alias `--input`) or sibling-detected next to `--output`; the run hard-fails if neither resolves. There is no `--demo` flag.
- **Do not overclaim scope**: this skill calls peaks, builds the ENCODE naive-overlap consensus, the featureCounts matrix, peak annotation, and post-peak QC — it does NOT run differential accessibility (`bulkatac-DA`), motif enrichment (`bulkatac-motif-enrichment`), or footprinting (`bulkatac-footprinting`).
- **Explain the run before execution**: state the effective `--qvalue` (default 0.05), `--overlap-fraction` (default 0.50, ENCODE standard), `--threads`, whether `--idr` is set (OFF by default, needs ≥ 2 replicates/condition), and `--skip-qc` / `--skip-annotation` if used. `--shift`/`--extsize` only affect single-end input.
- **Use wrapper-correct language**: annotation is silently skipped when neither a GTF nor HOMER is available; PCA + sample correlation need ≥ 2 conditions; the `qvalue<q>` tag is baked into every subdir so re-running a different `--qvalue` writes a parallel tree.
- **Preserve the contract**: successful runs emit `report.md`, `result.json`, `peak_calling_summary.csv`, `peaks/<sample>/qvalue<q>/`, `consensus/qvalue<q>/` (`consensus_peaks.bed`, `consensus_peaks.saf`, `peak_counts.txt`), `annotation/`, `qc_after_peak_calling/`, and `heatmap/`.
- **Interpret outputs correctly**: `peak_counts.txt` holds raw featureCounts fragment counts (columns 7+) for DESeq2/edgeR — do NOT normalise it here; the last row of `peak_calling_summary.csv` is the literal `consensus` row.
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkatac-peak-calling.md`.
