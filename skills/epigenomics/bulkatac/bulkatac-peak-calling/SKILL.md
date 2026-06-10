---
name: bulkatac-peak-calling
description: Load when calling peaks on bulk ATAC-seq deduplicated BAMs (MACS2), building ENCODE naive-overlap consensus peaks, generating a featureCounts matrix, annotating peaks, and computing post-peak QC (FRiP, TSS/peak heatmaps, PCA, IDR). Skip for scATAC (use scatac-preprocessing), ChIP-seq, or before BAMs are aligned (run bulkatac-mapping first).
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- atac-seq
- peak-calling
- macs2
- narrowpeak
- frip
- idr
- featurecounts
- deeptools
- homer
requires:
- pandas
- numpy
---

## When to use

The user has deduplicated, MAPQ-filtered BAMs from `bulkatac-mapping` and wants ENCODE Step 3 outputs: per-sample MACS2 peaks, an ENCODE naive-overlap consensus across conditions, a featureCounts peak × sample matrix ready for DESeq2 / edgeR, peak annotation against the genome's GTF (or HOMER), and post-peak QC (FRiP, TSS heatmap, peak-centered heatmap, PCA, sample correlation, optional IDR). Skip for scATAC (`scatac-preprocessing`), ChIP-seq, or to start from FASTQs / unaligned BAMs — run `bulkatac-mapping` first.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-2 result | `<project>/mapping/result.json` from `bulkatac-mapping` | Yes (via `--prev-result`, or sibling-detected from `--wd`) |
| GTF | Gene annotation (`.gtf` / `.gtf.gz`) for annotation + TSS heatmap | Optional; auto-detected from Step 2's `genome_files`; HOMER `annotatePeaks.pl` is the fallback |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Per-sample peaks + tier, consensus count, ENCODE thresholds, FRiP table |
| Result envelope | `<output>/result.json` | `peak_calling`, `consensus`, `genome_files`, chained from Step 2 |
| Per-sample summary | `<output>/peak_calling_summary.csv` | One row per sample — n_peaks, ENCODE tier |
| Per-sample peaks | `<output>/peaks/<sample>/qvalue<q>/` | MACS2 narrowPeak + summits.bed |
| Consensus set | `<output>/consensus/qvalue<q>/` | `consensus_peaks.bed`, `consensus_peaks.saf`, `peak_counts.txt` (featureCounts), per-condition pooled subdirs |
| Annotation | `<output>/annotation/qvalue<q>/` | Per-condition pies + TSS-distance histograms + cross-condition comparison panels |
| QC | `<output>/qc_after_peak_calling/{frip,pca,sample_correlation,IDR}/qvalue<q>/` | Bar/scatter PNGs + summary CSV |
| Heatmaps | `<output>/heatmap/qvalue<q>/` | TSS-centered + peak-centered deepTools heatmaps (all samples) |
| Reproducibility | `<output>/reproducibility/commands.sh` | Re-run command |

## Flow

1. Locate the upstream Step-2 `result.json`: use `--prev-result` if passed, otherwise the sibling `<project>/mapping/result.json` (`--wd`'s parent); hard-fail if neither resolves (`bulkatac-peak-calling.py:469-478`).
2. Reconstruct `MappingResult` list, `GenomeFiles`, per-sample BigWig paths and condition mapping from the Step-2 envelope; CLI `--gtf` overrides auto-detected GTF (`bulkatac-peak-calling.py:487-503`).
3. Compute MACS2 effective genome size from the build name (FASTA-derived fallback) (`bulkatac-peak-calling.py:506`).
4. Step 3a — `run_all_peak_calling`: per-sample MACS2 (BAMPE `--nomodel` for PE; `--shift -37 --extsize 73` for SE) at `--qvalue` (`bulkatac-peak-calling.py:523-531`).
5. Step 3a (cont.) — `build_consensus_peaks` (ENCODE naive overlap: pool BAMs per condition → MACS2 → intersect with each replicate at `--overlap-fraction`) → BED + SAF + featureCounts matrix (`bulkatac-peak-calling.py:533-551`).
6. Step 3b — `annotate_per_condition_peaks` (HOMER `annotatePeaks.pl` when available, else GTF-based `bedtools closest`) → per-condition pies + TSS histograms + cross-condition comparison plots (`bulkatac-peak-calling.py:555-597`).
7. Step 3c — FRiP per sample, TSS + peak heatmaps (deepTools), PCA + correlation (when ≥ 2 conditions), optional IDR with `--idr` (`bulkatac-peak-calling.py:599-658`).
8. Write `report.md`, `result.json`, `reproducibility/`, `README.md` and a stdout summary (`bulkatac-peak-calling.py:660-693`).

## Gotchas

- **No `--demo` flag.** `bulkatac-peak-calling.py:465` jumps straight to argparse + Step-2 loading. Smoke-test the full Step 1 → 2 → 3 chain by running `bulkatac-preprocessing --demo` first, then `bulkatac-mapping --wd <demo-wd>`, then this script with the same `--wd`.
- **Chains via `--prev-result` (also accepts `--input` as an alias).** `bulkatac-peak-calling.py:399-403` reads the upstream skill's `result.json`. `--wd` is aliased to `--output` (`bulkatac-peak-calling.py:404`) so the OmicsClaw runner's `--output <path>` + `--input <result.json>` injection works; if only `--output` is passed, sibling-detection finds `mapping/result.json` next to it (`<output>/../mapping/result.json`).
- **`--shift` / `--extsize` only matter for single-end input.** Per the docstring at `bulkatac-peak-calling.py:9-10`, PE BAMs are called with `--format BAMPE --nomodel` and the shift/extsize values are ignored; only SE BAMs use the `--shift -37 --extsize 73` half-nucleosome model. Layout (`is_paired`) comes from Step 2's sample sheet — there is no override.
- **Annotation silently skipped when no GTF AND no HOMER.** `bulkatac-peak-calling.py:593-597` emits a warning and leaves `annotation_result = None`. The report's Step 3b section will be missing. Provide `--gtf` or install HOMER (`conda install -c bioconda homer`) before re-running.
- **`--idr` is OFF by default and silently no-ops with too few replicates.** `bulkatac-peak-calling.py:431` documents IDR's cost (pseudo-replicate splitting + repeated MACS2 calls per condition). `run_all_idr` requires ≥ 2 replicates per condition; conditions with a single replicate are skipped without error — check `qc_after_peak_calling/IDR/qvalue<q>/` for sparser output than expected.
- **PCA + sample correlation need ≥ 2 conditions.** `bulkatac-peak-calling.py:641` checks `len(set(conditions_list)) >= 2`; single-condition runs silently skip both. The count matrix at `consensus_peaks.saf` is still produced — feed it to your own PCA / DESeq2 downstream.
- **Q-value tag is baked into every output subdirectory.** `bulkatac-peak-calling.py:521` derives `qvalue{q}` and prefixes most subdirs (`consensus/qvalue0.05/`, `annotation/qvalue0.05/`, `qc_after_peak_calling/frip/qvalue0.05/`). Re-running with a different `--qvalue` creates a parallel output tree rather than overwriting; clean up manually if disk pressure is a concern.

## Key CLI

End-to-end run after `bulkatac-mapping` (auto-detects Step-2 result, q ≤ 0.05):

```bash
python skills/epigenomics/bulkatac/bulkatac-peak-calling/bulkatac-peak-calling.py \
    --wd ./atac_run --threads 32
```

Stricter q-value + IDR reproducibility:

```bash
python skills/epigenomics/bulkatac/bulkatac-peak-calling/bulkatac-peak-calling.py \
    --wd ./atac_run --qvalue 0.01 --idr --threads 48
```

Annotate with a user-supplied GTF, skip post-peak QC (faster iteration):

```bash
python skills/epigenomics/bulkatac/bulkatac-peak-calling/bulkatac-peak-calling.py \
    --prev-result /tmp/atac/mapping/result.json \
    --wd /tmp/atac \
    --gtf /refs/hg38/gencode.v44.annotation.gtf.gz \
    --skip-qc --threads 32
```

## See also

- `references/parameters.md` — every CLI flag with type + default (auto-generated from `parameters.yaml`).
- `references/methodology.md` — MACS2 parameter derivation (PE BAMPE vs SE half-nucleosome), ENCODE naive-overlap algorithm, featureCounts SAF schema, HOMER vs bedtools annotation fallback, IDR pipeline.
- `references/output_contract.md` — full output tree, `peak_calling_summary.csv` + `peak_counts.txt` column schemas, `result.json` keys.
- Adjacent skills:
  - Upstream — `bulkatac-mapping` (must run first to produce `mapping/result.json` and dedup BAMs).
  - Downstream — `bulkatac-da` (differential accessibility from the consensus count matrix); `bulkatac-motif-enrichment` (HOMER motif enrichment on peaks); `bulkatac-footprinting` (TOBIAS on consensus peaks).
  - Parallel — `scatac-preprocessing` (single-cell ATAC; different peak-calling assumptions).
