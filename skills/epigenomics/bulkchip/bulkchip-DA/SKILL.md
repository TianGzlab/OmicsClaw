---
name: bulkchip-DA
description: Load when running differential binding analysis on bulk ChIP-seq consensus peak counts via pyDESeq2 — two-condition contrast, volcano plot, and IGV-ready BED tracks of gained/lost peaks. Skip for bulk ATAC (use bulkatac-DA), bulk RNA (use bulkrna-de), or before peaks are called (run bulkchip-peak-calling first).
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- chip-seq
- differential-binding
- pydeseq2
- deseq2
- volcano
- contrast
- bed-tracks
requires:
- pandas
- numpy
---

> **Status: scaffold.** Methodology docs complete; the entrypoint is wired
> (CLI + chaining) but its tool-backed body is not yet implemented and prints a
> methodology notice. Apply the methodology below until `_lib/DA.py` is filled in.

## When to use

The user has a consensus peak count matrix from `bulkchip-peak-calling` and wants to find peaks with differential binding between two conditions (e.g. treated vs control, or KO vs WT) via pyDESeq2 — size-factor normalization, Wald test, LFC shrinkage, a volcano plot, and BED tracks of gained/lost peaks. Skip for bulk ATAC (`bulkatac-DA`), bulk RNA (`bulkrna-de`), or before peaks exist (run `bulkchip-peak-calling` first).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-3 result | `<project>/peak_calling/result.json` (with `consensus.count_matrix`) | Yes (via `--prev-result`, or sibling-detected from `--wd`) |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Contrast, n up/down, top peaks, thresholds |
| Result envelope | `<output>/result.json` | `differential_binding`, chained from Step 3 |
| DB table | `<output>/differential_binding.csv` | peak, baseMean, log2FC, pvalue, padj |
| Volcano | `<output>/volcano.png` | log2FC vs -log10 padj |
| Up/down tracks | `<output>/{up,down}_peaks.bed` | IGV-ready gained/lost peaks |

## Flow

1. Locate Step-3 `result.json`; load `consensus.count_matrix` (featureCounts peaks × samples).
2. Build the design from the sample sheet's `condition`; resolve `--treat` / `--control` (default: the two conditions, alphabetical).
3. `run_differential_binding` — pyDESeq2: size factors, dispersion, Wald test, `apeglm`/`ashr` LFC shrinkage.
4. Threshold at `--padj` / `--lfc`; write volcano + up/down BED tracks.
5. Write `report.md`, `result.json`, `reproducibility/`, `README.md`.

## Gotchas

- **Counts must be raw.** `peak_counts.txt` from Step 3 is raw featureCounts; pyDESeq2 does its own size-factor normalization — do not pre-normalise.
- **Needs ≥ 2 conditions with replicates.** A single condition (or no replicates) cannot be contrasted; the run errors with an actionable message.
- **Binding ≠ expression.** Differential binding measures changes in ChIP signal at peaks (factor occupancy / mark deposition), not transcript abundance — interpret in that frame.
- **Chains via `--prev-result` (alias `--input`)**; `--output` aliases `--wd`. Mirrors `bulkatac-DA` (same count-matrix schema, identical DESeq2 path).

## Key CLI

```bash
python skills/epigenomics/bulkchip/bulkchip-DA/bulkchip-DA.py \
    --wd ./chip_run/DA --treat treated --control control
```

Stricter thresholds:

```bash
python skills/epigenomics/bulkchip/bulkchip-DA/bulkchip-DA.py \
    --wd ./chip_run/DA --treat KO --control WT --padj 0.01 --lfc 1.5
```

## See also

- `references/parameters.md` — every CLI flag with type + default.
- `references/methodology.md` — pyDESeq2 contrast, LFC shrinkage, thresholding, ChIP-vs-RNA interpretation.
- `references/output_contract.md` — output tree + `differential_binding.csv` / `result.json` schemas.
- Adjacent skills:
  - Upstream — `bulkchip-peak-calling` (Step 3: consensus count matrix).
  - Downstream — `bulkchip-motif-enrichment` / `bulkchip-annotation-enrichment` (run on up/down peak subsets).
  - Parallel — `bulkatac-DA` (bulk ATAC differential accessibility).
