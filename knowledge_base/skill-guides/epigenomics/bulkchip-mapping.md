---
doc_id: skill-guide-bulkchip-mapping
title: OmicsClaw Skill Guide — Bulk ChIP Mapping
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkchip-mapping, bulkchip-alignment]
search_terms: [bulk ChIP mapping, Bowtie2, BWA, ENCODE BAM filter, NRF PBC, NSC RSC cross-correlation, deepTools fingerprint]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ChIP Mapping

**Status**: scaffold-stage guide for `bulkchip-mapping`. The entrypoint is a
methodology scaffold; apply this methodology directly. ENCODE ChIP-seq Step 2.

## Purpose

Decide whether trimmed reads are ready for alignment, and how to assess
ChIP-specific signal-to-noise — which uses **NSC/RSC cross-correlation and the
deepTools fingerprint**, not ATAC's TSS-enrichment / fragment-length QC.

## Step 1: Inspect The Data First

- **Upstream**: chains off `<project>/preprocessing/result.json` (`--prev-result`
  / `--input`, or sibling-detected from `--wd`).
- **Reference**: `--genome` + a supplied index (`--bowtie2-index`/`--bwa-index`)
  or auto-built in `--ref-dir`.
- **Controls**: input/IgG samples are aligned identically and carried forward.
- **External tools**: bowtie2/bwa, samtools, deeptools, phantompeakqualtools
  (`run_spp.R`) or ssp.

## Step 2: Understand The Method Path

- **Align**: Bowtie2 (default, `--very-sensitive`) or BWA MEM.
- **ENCODE filter**: `-F 1804 -f 2 -q 30` (PE) / `-F 1796 -q 30` (SE); dedup
  `samtools markdup -r`; optional blacklist removal.
- **Complexity**: NRF, PBC1, PBC2 (ENCODE ChIP PBC2 bar > 10).
- **ChIP QC**:
  - Cross-correlation (run_spp.R / ssp) → NSC (acceptable > 1.05),
    RSC (acceptable > 0.8), fragment-length estimate.
  - deepTools fingerprint → ChIP-vs-input enrichment, JS distance.
  - RPGC bigWig.
- **No Tn5 shift** — the offset is handled by MACS2 (SE) in Step 3.

## Step 3: Tune Parameters

1. `--aligner` (bowtie2 vs bwa) — convention; contracts unchanged.
2. `--no-blacklist` / `--blacklist` — blacklist handling.
3. `--downsample` — equalize depth across samples.
4. `--skip-qc` — skip Step 2b for a fast alignment-only pass.

## Step 4: What To Say After The Run

- Report align rate, NRF/PBC1/PBC2 per sample, and NSC/RSC + fingerprint per
  ChIP sample with ENCODE tiers.
- If NSC < 1.05 or RSC < 0.8: weak enrichment / high background — flag and
  cross-check the fingerprint curve.
- Do NOT report TSS enrichment or fragment-length NFR (ATAC-only). Chain
  `mapping/result.json` into `bulkchip-peak-calling`.
