---
name: bulkchip-peak-annotation
description: "Load when annotating bulk ChIP-seq peaks to features + nearest genes (HOMER annotatePeaks.pl, GTF fallback) and extracting target genes within a TSS window. Annotates consensus peaks, auto-adding DA up/down peaks when a bulkchip-DA result exists. Skip for GO/KEGG enrichment (bulkchip-enrichment), motif analysis (bulkchip-motif-enrichment), or before peaks are called."
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- chip-seq
- peak-annotation
- target-genes
- tss
- homer
- chipseeker
requires:
- pandas
- numpy
- matplotlib
---

> **Status: implemented.** HOMER `annotatePeaks.pl` annotation with a GTF
> `bedtools closest` fallback and graceful feature-less degradation when
> neither a HOMER genome nor a GTF is available. GO/KEGG enrichment is a
> **separate** skill that consumes this skill's `result.json` target genes.

## When to use

The user has ChIP-seq peaks from `bulkchip-peak-calling` (consensus / per-condition) or differential peaks from `bulkchip-DA` (up/down) and wants to assign each peak to a genomic feature (promoter-TSS / exon / intron / intergenic / ...) and its nearest gene, then derive the set of target genes whose TSS lies within a chosen window. Run it after peak-calling: by default it annotates the **consensus** peaks (the genome-wide binding landscape) and, when a `bulkchip-DA` result is reachable, **also** annotates the DA **up/down** peaks in the same run (per-subset outputs). This is the annotation half of the ChIP-seq downstream that replaces the ATAC suite's footprinting. Skip for motif discovery (`bulkchip-motif-enrichment`), for GO/KEGG over-representation (`bulkchip-enrichment`), or before peaks exist.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-3 result | `<project>/peak_calling/result.json` (`consensus.consensus_bed`, `peak_calling[].peaks_file`, `sample_sheet.genome`, optional `genome_files.gtf`) | Yes (via `--prev-result`, or sibling-detected from `--wd`) |
| DA result | `bulkchip-DA` result.json (`differential_binding.up_bed`/`down_bed`) | Only for `--peak-subset up/down` (via `--de-result`, or chained) |
| GTF | Gene annotation | Optional; `--gtf` overrides auto-detected `genome_files.gtf`; HOMER genome fallback |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Feature distribution, top target genes, figures |
| Result envelope | `<output>/result.json` | top-level `annotation` block = consensus (feature_counts, target_genes, figures) for back-compat; `annotations[]` lists every annotated subset |
| Annotation (consensus) | `<output>/annotation/` | `annotated_peaks.tsv`, `peak_annotation_summary.csv`, feature pie, TSS-distance histogram |
| Annotation (DA) | `<output>/annotation_up/`, `<output>/annotation_down/` | same files for the gained/lost peaks (only when a DA result is reachable) |
| Reproducibility | `<output>/reproducibility/` | `commands.sh`, `requirements.txt` |

## Flow

1. Locate the upstream `result.json` and decide the subset list: with the default `--peak-subset consensus`, that is `consensus` plus `up`+`down` whenever a DA result is reachable (`--de-result`, the chained-in DA result, or the sibling `<project>/DA/result.json`) and `--consensus-only` is not set; an explicit `up`/`down`/`condition` annotates only that one subset.
2. For each subset, resolve its peak BED (consensus / first per-condition peaks from Step 3, or DA `up`/`down`) and the genome/GTF (`--gtf` > auto-detected `genome_files.gtf`; `--genome`/`sample_sheet.genome` is the HOMER-genome fallback; for `up`/`down` the DA result's `prev_result` is followed back to peak-calling).
3. `annotate_peaks` per subset — HOMER `annotatePeaks.pl` (`-gtf` if a GTF is available, else the genome name) → feature category + nearest gene + distance per peak; GTF `bedtools closest` fallback (Promoter / Proximal / Distal / Intergenic) when HOMER is unavailable; graceful feature-less output when neither is available (no crash). Consensus → `annotation/`, DA subsets → `annotation_up/` / `annotation_down/`.
4. Per subset: feature-distribution donut + TSS-distance histogram, and the target-gene set (unique nearest genes whose absolute TSS distance ≤ `--tss-window`).
5. Write a multi-section `report.md`, `result.json` (top-level `annotation` = consensus for `bulkchip-enrichment`; `annotations[]` = all subsets), `reproducibility/`, `README.md`.

## Gotchas

- **Annotation only.** GO/KEGG enrichment is a separate skill — this one stops at the target-gene list. `bulkchip-enrichment` reads the **consensus** target genes from the top-level `annotation.target_genes` (so the auto multi-subset behavior doesn't change what enrichment consumes).
- **DA up/down are auto-added, not required.** With the default subset, up/down are annotated only if a DA result is reachable; if none is found the skill simply does consensus-only (no error). Pass `--consensus-only` to force consensus-only even when a DA result exists, or `--de-result` to point at a specific DA `result.json`.
- **GTF or HOMER genome required for features.** With neither, the skill still emits a well-formed `annotated_peaks.tsv` (peaks pass through, no feature/gene) and warns — it does not crash. Provide `--gtf` for the richest annotation.
- **`--tss-window` controls target-gene calls** — widen it (e.g. 10000) for enhancer-associated marks (H3K27ac/H3K4me1), keep tight (3000) for promoter marks/TFs.

## Key CLI

```bash
# Default: annotate consensus + auto-add DA up/down (sibling DA/result.json detected):
python skills/epigenomics/bulkchip/bulkchip-peak-annotation/bulkchip-peak-annotation.py \
    --input ./chip_run/peak_calling/result.json --output ./chip_run/annotation --tss-window 3000
```

Consensus only, or a single differential subset (enhancer window):

```bash
# just the consensus peaks
python .../bulkchip-peak-annotation.py --input ./chip_run/peak_calling/result.json \
    --output ./chip_run/annotation --consensus-only

# only the gained peaks from a contrast
python .../bulkchip-peak-annotation.py --input ./chip_run/peak_calling/result.json \
    --output ./chip_run/annotation --peak-subset up \
    --de-result ./chip_run/DA/result.json --tss-window 10000
```

## See also

- `references/methodology.md` — annotation categories, fallback ladder, TSS-window target-gene rule.
- Adjacent skills:
  - Upstream — `bulkchip-peak-calling` (Step 3); `bulkchip-DA` (Step 4, for up/down subsets).
  - Downstream — bulkchip functional-enrichment skill (GO/KEGG on `annotation.target_genes`).
  - Sibling — `bulkchip-motif-enrichment` (HOMER motif enrichment).
  - Parallel — `bulkatac-footprinting` (the ATAC-only downstream this replaces for ChIP).
