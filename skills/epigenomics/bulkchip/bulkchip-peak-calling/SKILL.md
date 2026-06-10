---
name: bulkchip-peak-calling
description: Load when calling ChIP-seq peaks on dedup BAMs with MACS2 against the matched input control — narrow (TF/sharp) or --broad (broad histone), ENCODE naive-overlap consensus, featureCounts matrix, FRiP, and optional IDR. Skip for bulk ATAC (use bulkatac-peak-calling), or before BAMs are aligned (run bulkchip-mapping first).
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- chip-seq
- peak-calling
- macs2
- narrowpeak
- broadpeak
- input-control
- consensus
- frip
- idr
- featurecounts
requires:
- pandas
- numpy
---

> **Status: scaffold.** Methodology docs complete; the entrypoint is wired
> (CLI + chaining) but its tool-backed body is not yet implemented and prints a
> methodology notice. Apply the methodology below until `_lib/peak_calling.py`
> is filled in.

## When to use

The user has dedup ChIP + control BAMs from `bulkchip-mapping` and wants ENCODE Step 3: per-sample MACS2 peaks **called against the matched input/IgG control**, narrow (TF / sharp histone) or `--broad` (broad histone) peaks, an ENCODE naive-overlap consensus across conditions, a featureCounts peak × sample matrix for `bulkchip-DA`, FRiP, and optional IDR reproducibility. Skip for bulk ATAC (`bulkatac-peak-calling`, which has no control), or to start from FASTQs / unaligned BAMs (run `bulkchip-mapping` first). Peak **annotation + functional enrichment** is a separate skill (`bulkchip-annotation-enrichment`).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-2 result | `<project>/mapping/result.json` (with dedup BAMs + `control_map`) | Yes (via `--prev-result`, or sibling-detected from `--wd`) |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Per-sample peaks + FRiP, consensus count, ENCODE thresholds |
| Result envelope | `<output>/result.json` | `peak_calling`, `consensus`, chained from Step 2 |
| Per-sample summary | `<output>/peak_calling_summary.csv` | n_peaks + FRiP per sample + consensus row |
| Per-sample peaks | `<output>/peaks/<sample>/` | MACS2 narrowPeak (+summits) or broadPeak |
| Consensus set | `<output>/consensus/` | `consensus_peaks.bed/.saf`, `peak_counts.txt` (featureCounts) |
| QC | `<output>/qc/{frip,IDR}/` | FRiP bar + optional IDR |

## Flow

1. Locate the Step-2 `result.json`; reconstruct ChIP/control BAM pairs from `control_map`.
2. Resolve per-sample peak mode (`--peak-mode auto` infers from antibody label; `narrow`/`broad` force).
3. Step 3a — `run_all_peak_calling`: `macs2 callpeak -t <chip> -c <control>` at `--qvalue` (narrow) or `--broad --broad-cutoff` (broad).
4. Step 3b — `build_consensus_peaks` (ENCODE naive overlap: pool replicate ChIP BAMs per condition → re-call vs pooled control → intersect each replicate at `--overlap-fraction`) → BED + SAF + featureCounts matrix.
5. Step 3c — FRiP per sample; optional IDR with `--idr` (point-source, true replicates).
6. Write `report.md`, `result.json`, `reproducibility/`, `README.md`.

## Gotchas

- **Control is used when present, not mandatory.** A ChIP sample with a resolvable input/IgG control (from Step 2's `control_map`) is called `MACS2 -c <control>`. A ChIP sample with **no** control is still called — MACS2 runs **without `-c`** and builds the background from the ChIP itself (local lambda), at both the per-sample and pooled-consensus levels. This is supported end-to-end but lower-confidence (ENCODE recommends a matched input); a warning is logged for each control-free sample. ChIP-vs-input QC (deepTools fingerprint + `bamCompare` log2 track in Step 2b) is simply skipped when there is no control.
- **Narrow vs broad.** TFs and sharp marks (H3K4me3, H3K27ac) use narrow `--qvalue`; broad marks (H3K9me3, H3K27me3, H3K36me3, ...) use `--broad --broad-cutoff`. `--peak-mode auto` infers from the antibody label via `_lib.encode_qc_criteria.infer_peak_mode`; override explicitly when in doubt.
- **This skill stops at the count matrix + FRiP.** It does NOT annotate peaks, run GO/KEGG (`bulkchip-annotation-enrichment`), find motifs (`bulkchip-motif-enrichment`), or run differential binding (`bulkchip-DA`).
- **`peak_counts.txt` is raw featureCounts** — feed columns 7+ to DESeq2/edgeR; do not normalise here.
- **IDR is off by default** and silently no-ops for conditions with a single replicate; broad-mode IDR is not meaningful (point-source only).

## Key CLI

```bash
python skills/epigenomics/bulkchip/bulkchip-peak-calling/bulkchip-peak-calling.py \
    --wd ./chip_run/peak_calling --peak-mode auto --threads 32
```

Force broad histone peaks + IDR reproducibility:

```bash
python skills/epigenomics/bulkchip/bulkchip-peak-calling/bulkchip-peak-calling.py \
    --wd ./chip_run/peak_calling --peak-mode broad --broad-cutoff 0.1 --idr
```

## See also

- `references/parameters.md` — every CLI flag with type + default.
- `references/methodology.md` — MACS2 -c control rationale, narrow vs broad derivation, naive-overlap consensus, featureCounts SAF, IDR.
- `references/output_contract.md` — output tree + `peak_calling_summary.csv` / `peak_counts.txt` / `result.json` schemas.
- Adjacent skills:
  - Upstream — `bulkchip-mapping` (Step 2).
  - Downstream — `bulkchip-DA` (differential binding); `bulkchip-motif-enrichment`; `bulkchip-annotation-enrichment`.
  - Parallel — `bulkatac-peak-calling` (bulk ATAC; no control, narrow-only).
