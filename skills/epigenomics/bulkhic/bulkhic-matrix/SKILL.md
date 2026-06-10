---
name: bulkhic-matrix
description: "Load when turning Hi-C .pairs into a balanced contact matrix: cooler cload, balance (ICE), zoomify into a multi-resolution .mcool, with P(s) distance-decay QC (cooltools expected-cis). Writes .mcool by default (every downstream skill reads it); --format both also exports a Juicebox .hic. Skip for ATAC/ChIP; downstream are bulkhic-compartments/tads/loops/pileup."
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
  - epigenomics
  - hi-c
  - cooler
  - mcool
  - contact-matrix
  - ice-balancing
  - cooltools
requires:
  - cooler
  - cooltools
  - numpy
  - pandas
  - matplotlib
---

> **Status: implemented** (cooler + cooltools). Step 3 of the bulk Hi-C suite.

## When to use

The user has QC'd `.pairs` from `bulkhic-mapping` and wants a balanced,
multi-resolution contact matrix (`.cool`/`.mcool`) plus the P(s) decay QC that
all downstream analyses depend on. Optionally also a `.hic` for Juicebox. Skip
for ATAC/ChIP. Downstream: compartments / insulation / loops / pileup.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-2 result | `<project>/mapping/result.json` (`mapping[].pairs` + `genome_files.chrom_sizes/genome/fasta`) | Yes (via `--prev-result`, or sibling-detected) |
| juicer jar | `juicer_tools.jar` | Optional (`--juicer-jar`, for `.hic`) |

| Output | Path | Notes |
|---|---|---|
| Matrix | `<output>/<sample>/<sample>.mcool` (+ `.cool`) | ICE-balanced, multi-resolution |
| Combined matrix | `<output>/<condition>_combined/<condition>_combined.mcool` | per-condition replicate pool (≥2 reps); skip with `--no-combine` |
| P(s) | `<output>/<sample>/<sample>.Pofs.*.png` + `expected_cis.*.tsv` | contact-decay QC |
| .hic | `<output>/<sample>/<sample>.hic` | optional Juicebox export |
| Result envelope | `<output>/result.json` | `matrix[]` (mcool, resolutions, `combined`/`condition`/`members`) + carried `genome_files` (incl. FASTA for compartments) |

## Flow

1. Load Step-2 → `.pairs` paths + genome + chrom.sizes.
2. Per sample: `cooler cload pairs` (base binsize) → `cooler balance --mad-max 5` → `cooler zoomify --balance -r <resolutions>` → `.mcool`.
3. P(s) decay: `cooltools expected-cis` at the QC resolution + a log-log plot.
4. Per condition with ≥2 replicates: `cooler merge` the replicate base `.cool`s → one pooled base cool → balance + zoomify → `<condition>_combined.mcool` (same P(s)/`.hic` treatment). Added to `matrix[]` so it flows downstream. Disable with `--no-combine`.
5. Optional `.hic`: convert pairs → juicer short format → `juicer_tools pre` (graceful skip without Java/jar).
6. Write `report.md`, `result.json` (carries `genome_files` forward), `reproducibility/`, `README.md`.

## Gotchas

- **Resolutions must be multiples of `--base-binsize`** (cooler zoomify requirement); defaults are all multiples of 1 kb.
- **`.hic` is export-only** — analysis stays in cooltools; `.hic` needs Java + a juicer jar and is skipped gracefully otherwise (no GPU / HiCCUPS).
- **FASTA is carried forward** in `genome_files` so `bulkhic-compartments` can build its GC phasing track.
- **Resolution guidance**: compartments ~100 kb–1 Mb, insulation/TADs ~10–50 kb, loops ~5–10 kb — keep those in the `.mcool` pyramid.
- **Combined matrices pool raw counts** (`cooler merge` sums contacts, then re-balance) — the standard way to deepen per-condition coverage. Single-replicate conditions are not pooled. Pooling loses replicate-to-replicate variability, so use replicate matrices for reproducibility/QC and the pooled matrix for calling sparse features (loops/TADs).

## Key CLI

```bash
python skills/epigenomics/bulkhic/bulkhic-matrix/bulkhic-matrix.py \
    --prev-result ./hic_run/mapping/result.json --wd ./hic_run/matrix --threads 32
# with Juicebox export:
python .../bulkhic-matrix.py --prev-result ./hic_run/mapping/result.json \
    --wd ./hic_run/matrix --juicer-jar ./tools/juicer_tools.jar
```

## See also

- `references/methodology.md` — cload columns, ICE balancing, zoomify, P(s), .hic export.
- Upstream — `bulkhic-mapping`. Downstream — `bulkhic-compartments` / `bulkhic-tads` / `bulkhic-loops` / `bulkhic-pileup`.
