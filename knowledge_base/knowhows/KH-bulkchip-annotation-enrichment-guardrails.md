---
doc_id: bulkchip-annotation-enrichment-guardrails
title: Bulk ChIP Annotation & Enrichment Guardrails
doc_type: knowhow
critical_rule: MUST verify an upstream peak-calling/DA result.json is chained in, require a GTF or HOMER genome, explain the peak subset + TSS window + gene-set libraries before running, and never claim motif discovery or differential binding — this skill annotates peaks to genes and runs GO/KEGG over the target-gene set
domains: [epigenomics]
related_skills: [bulkchip-annotation-enrichment, bulkchip-annotation_enrichment, bulkchip-annotation, bulkchip-enrichment]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ChIP peak annotation, functional enrichment, GO, KEGG, gseapy, enrichr, ChIPseeker, target genes, ChIP注释富集]
priority: 1.0
---

# Bulk ChIP Annotation & Enrichment Guardrails

- **Scaffold status**: methodology scaffold — the entrypoint prints a notice and does not execute tools yet. Apply the methodology in the skill guide / `references/methodology.md`.
- **Inspect first**: confirm an upstream `result.json` is resolvable — `bulkchip-peak-calling` (consensus / per-condition) or `bulkchip-DA` (up/down via `--de-result`).
- **Require an annotation source**: needs a GTF (auto-detected from upstream `genome_files`, or `--gtf`) or a HOMER genome; with neither, annotation cannot run — flag this before claiming results.
- **Explain the run before execution**: state `--peak-subset`, `--tss-window` (default 3000 bp; widen to ~10 kb for enhancer marks like H3K27ac/H3K4me1), `--gene-sets` (default GO_Biological_Process,KEGG), `--organism`.
- **Two stages**: annotation (peak→feature/gene) always runs; GO/KEGG enrichment depends on a non-empty target-gene set — a mostly-intergenic peak set yields few target genes and sparse enrichment, which is a real result, not an error.
- **Do not overclaim scope**: this skill annotates peaks + runs functional enrichment — it does NOT find sequence motifs (`bulkchip-motif-enrichment`) or run differential binding (`bulkchip-DA`).
- **Preserve the contract**: successful runs emit `report.md`, `result.json`, `annotation_enrichment_summary.csv`, `annotation/` (`annotated_peaks.tsv`, feature pie, TSS-distance), `enrichment/` (per-library GO/KEGG CSVs + dotplots).
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkchip-annotation-enrichment.md`.
