---
doc_id: skill-guide-bulkchip-annotation-enrichment
title: OmicsClaw Skill Guide — Bulk ChIP Annotation & Enrichment
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkchip-annotation-enrichment, bulkchip-annotation_enrichment, bulkchip-annotation, bulkchip-enrichment]
search_terms: [bulk ChIP peak annotation, functional enrichment, GO, KEGG, gseapy, enrichr, ChIPseeker, target genes]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ChIP Annotation & Enrichment

**Status**: scaffold-stage guide for `bulkchip-annotation-enrichment`. The
entrypoint is a methodology scaffold; apply this methodology directly. ChIP-seq
Step 5b — the ChIP-relevant downstream that replaces ATAC's footprinting.

## Purpose

Decide how to map ChIP peaks to genes/features and run GO/KEGG over the
resulting target-gene set to learn what the bound regions regulate.

## Step 1: Inspect The Data First

- **Upstream**: `bulkchip-peak-calling` (consensus / per-condition) or
  `bulkchip-DA` (up/down via `--de-result`).
- **Annotation source**: a GTF (auto-detected from upstream `genome_files`, or
  `--gtf`) or a HOMER genome — flag if neither is available.
- **External tools**: HOMER (`annotatePeaks.pl`) or bedtools; gseapy.

## Step 2: Understand The Method Path

- **Annotation**: HOMER `annotatePeaks.pl` (rich feature categories) or GTF
  `bedtools closest` fallback → per-peak feature + nearest gene + TSS distance;
  feature-distribution pie + TSS-distance histogram.
- **Target genes**: genes whose TSS is within `--tss-window` of a peak.
- **Enrichment**: `gseapy.enrichr(target_genes, gene_sets=<--gene-sets>,
  organism=<--organism>)` → one CSV + dotplot per library.

## Step 3: Tune Parameters

1. `--peak-subset` (up/down need `--de-result`).
2. `--tss-window` — tight (~3 kb) for promoter marks / TFs; wide (~10 kb) for
   enhancer marks (H3K27ac/H3K4me1).
3. `--gene-sets`, `--organism`.

## Step 4: What To Say After The Run

- Report the feature distribution (promoter-TSS / intron / intergenic / ...),
  the number of target genes, and the top GO/KEGG terms with adjusted p-values.
- A mostly-intergenic peak set yielding few target genes / sparse enrichment is
  a real result, not an error.
- Do NOT claim sequence-motif discovery (`bulkchip-motif-enrichment`) or
  differential binding (`bulkchip-DA`).
