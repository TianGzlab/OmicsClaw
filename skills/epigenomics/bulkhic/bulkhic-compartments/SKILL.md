---
name: bulkhic-compartments
description: "Load when calling A/B compartments from a balanced Hi-C .mcool: cooltools expected-cis, eigs-cis (E1 eigenvector, GC-phased to sign A/B), and saddle on a main-chromosome view, plus a compartment-strength scalar. Coarse resolution (~50kb-1Mb). Skip for TADs (bulkhic-tads) or loops (bulkhic-loops); needs bulkhic-matrix output first."
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
  - epigenomics
  - hi-c
  - compartment
  - eigenvector
  - saddle
  - cooltools
requires:
  - cooler
  - cooltools
  - bioframe
  - numpy
  - pandas
  - matplotlib
---

> **Status: implemented** (cooltools). Downstream Step 4a of the bulk Hi-C suite.

## When to use

The user has a balanced `.mcool` from `bulkhic-matrix` and wants the genome's
A/B compartmentalisation: the first cis eigenvector (E1), GC-phased so positive
= A (active, gene-rich) and negative = B, plus a saddle plot quantifying
compartment strength. This is the coarse-scale (~100 kb–1 Mb) 3D-genome layer.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-3 result | `<project>/matrix/result.json` (`matrix[].mcool` + `genome_files.fasta`) | Yes |

| Output | Path | Notes |
|---|---|---|
| E1 track | `<output>/<sample>/*.eigs.*.cis.vecs.tsv` | per-bin eigenvectors |
| A/B BED | `<output>/<sample>/*.AB.*.bed` | E1-sign compartment calls |
| Saddle | `<output>/<sample>/*.saddle.*.{npz,png}` | compartment-strength matrix + heatmap |
| Result | `<output>/result.json` | `compartments[]` paths, chained `genome_files` |

## Flow

1. Load Step-3 → `.mcool` paths + FASTA.
2. Per sample: build a main-chromosome `--view` (drops tiny scaffolds); `cooltools expected-cis --view`; GC track (`bioframe.frac_gc`, or user `--phasing-track`); `cooltools eigs-cis --view --phasing-track`; binarise E1 → A/B BED; `cooltools saddle --view`; compute strength `(AA·BB)/AB²` → `*.strength.*.tsv`.
3. Write report / result.json / reproducibility / README.

## Gotchas

- **GC phasing needs the FASTA** (carried forward from `bulkhic-matrix`); without it eigs runs unphased and A/B sign is arbitrary.
- **Coarse resolution** — default 100 kb; finer bins add noise, not structure.
- **Graceful** — any missing tool / failed step degrades to a partial result, not a crash.

## Key CLI

```bash
python skills/epigenomics/bulkhic/bulkhic-compartments/bulkhic-compartments.py \
    --prev-result ./hic_run/matrix/result.json --wd ./hic_run/compartments --resolution 100000
```

## See also

- `references/methodology.md` — eigendecomposition, GC phasing, saddle.
- Upstream — `bulkhic-matrix`. Siblings — `bulkhic-tads`, `bulkhic-loops`. Aggregate — `bulkhic-pileup`.
