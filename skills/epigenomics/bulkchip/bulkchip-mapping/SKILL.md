---
name: bulkchip-mapping
description: Load when aligning bulk ChIP-seq reads (BWA-MEM2 default / BWA / Bowtie2), applying ENCODE BAM filtering + dedup, computing library complexity (NRF/PBC1/PBC2), and ChIP signal-to-noise QC — strand cross-correlation (NSC/RSC) and deepTools fingerprint. Skip for bulk ATAC (use bulkatac-mapping), or before reads are trimmed (run bulkchip-preprocessing first).
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- chip-seq
- mapping
- bwa-mem2
- bwa
- bowtie2
- encode-qc
- nrf
- pbc
- cross-correlation
- nsc-rsc
- fingerprint
- deeptools
requires:
- pandas
- numpy
---

> **Status: scaffold.** Methodology docs are complete; the entrypoint is wired
> (CLI + chaining) but its tool-backed body is not yet implemented and prints a
> methodology notice. Apply the methodology below until `_lib/mapping.py` and
> `_lib/QC_after_mapping.py` are filled in.

## When to use

The user has trimmed ChIP + control FASTQs from `bulkchip-preprocessing` and wants ENCODE Step 2: alignment, ENCODE BAM filtering + dedup, library-complexity metrics (NRF/PBC1/PBC2), and the **ChIP-specific signal-to-noise QC** — strand cross-correlation (NSC/RSC) and a deepTools ChIP-vs-input fingerprint — plus RPGC bigWig tracks. Skip for bulk ATAC (`bulkatac-mapping`, which uses TSS enrichment + fragment-length QC instead), or to start from raw FASTQs (run `bulkchip-preprocessing` first).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-1 result | `<project>/preprocessing/result.json` | Yes (via `--prev-result`, or sibling-detected from `--wd`) |
| Reference | genome build (`--genome`) + index (`--bwa-mem2-index`/`--bwa-index`/`--bowtie2-index`) or auto-built in `--ref-dir` | Yes |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Per-sample align%/NRF/PBC, NSC/RSC, fingerprint, ENCODE thresholds |
| Result envelope | `<output>/result.json` | `mapping`, `qc_after_mapping`, `genome_files`, `control_map`, chained from Step 1 |
| Per-sample summary | `<output>/mapping_summary.csv` | align rate, NRF/PBC1/PBC2 per sample |
| BAMs | `<output>/bam/` | dedup BAMs (ChIP + control), full-depth |
| BigWigs | `<output>/bigwig/` | per-sample RPGC tracks + `*.log2_input.bw` log2(ChIP/input) tracks |
| ChIP QC | `<output>/qc_after_mapping/{cross_correlation,fingerprint}/` | NSC/RSC + fingerprint PNGs + summary CSV |

## Flow

1. Locate the Step-1 `result.json` (`--prev-result`, else sibling `<wd>/../preprocessing/result.json`); reconstruct the sample sheet incl. `control_map`.
2. Resolve genome index (supplied `--bwa-mem2-index`/`--bwa-index`/`--bowtie2-index` or auto-build in `--ref-dir`).
3. Step 2a — `run_all_mapping`: align (BWA-MEM2 default; BWA / Bowtie2 optional), ENCODE filter (`-F 1804 -f 2 -q 30` PE), chrM removal, dedup (`samtools markdup -r`), optional blacklist removal, NRF/PBC. **Controls are aligned identically.**
4. Step 2b — `run_all_qc_after_mapping`: NSC/RSC cross-correlation (phantompeakqualtools/ssp), deepTools fingerprint (ChIP vs matched input), RPGC bigWig. Skipped with `--skip-qc`.
5. Write `report.md`, `result.json` (carrying `mapping` + `control_map` + `genome_files`), `reproducibility/`, `README.md`.

## Gotchas

- **No Tn5 shift.** Unlike ATAC, ChIP BAMs are not `+4/-5` shifted; the fragment-length offset is estimated by cross-correlation and applied by MACS2 in Step 3 (SE) — pre-shifting would double-correct.
- **ChIP QC ≠ ATAC QC.** This skill computes NSC/RSC + fingerprint, **not** TSS enrichment or the fragment-length nucleosome ladder (those are ATAC-specific). NSC > 1.05 and RSC > 0.8 are the ENCODE acceptable bars.
- **PBC2 bar is stricter than ATAC** — ENCODE ChIP wants PBC2 > 10 (ATAC: > 3). See `_lib/encode_qc_criteria.py`.
- **Controls flow through.** Input/IgG BAMs are produced and recorded in `result.json["mapping"]` with `is_control=true`; `bulkchip-peak-calling` pairs them via `control_map`.
- **Chains via `--prev-result` (alias `--input`)**; `--output` aliases `--wd`. If only `--output` is given, sibling-detection finds `preprocessing/result.json`.

## Key CLI

```bash
python skills/epigenomics/bulkchip/bulkchip-mapping/bulkchip-mapping.py \
    --prev-result ./chip_run/preprocessing/result.json \
    --wd ./chip_run/mapping --genome hg38 --threads 32
```

Use an existing Bowtie2 index, skip ChIP QC for a fast pass:

```bash
python skills/epigenomics/bulkchip/bulkchip-mapping/bulkchip-mapping.py \
    --wd ./chip_run/mapping --bowtie2-index /refs/hg38/bowtie2/hg38 --skip-qc
```

## See also

- `references/parameters.md` — every CLI flag with type + default.
- `references/methodology.md` — BWA-MEM2/BWA/Bowtie2 params, ENCODE filter flags, NRF/PBC formulas, NSC/RSC + fingerprint definitions and thresholds.
- `references/output_contract.md` — output tree + `mapping_summary.csv` / `result.json` schemas.
- Adjacent skills:
  - Upstream — `bulkchip-preprocessing` (Step 1).
  - Downstream — `bulkchip-peak-calling` (Step 3: MACS2 vs control).
  - Parallel — `bulkatac-mapping` (bulk ATAC; TSS/fragment QC instead of NSC/RSC).
