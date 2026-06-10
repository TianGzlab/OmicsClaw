---
name: bulkhic-tads
description: "Load when calling TADs from a balanced Hi-C .mcool: cooltools insulation (diamond window 8x resolution) plus Li boundary calling, then boundaries to TAD domains, across multiple resolutions. Adds a HiC-bench-style TAD PCA on per-bin insulation. Main-chromosome view. Skip for compartments (bulkhic-compartments) or loops (bulkhic-loops); needs bulkhic-matrix output first."
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
  - epigenomics
  - hi-c
  - tad
  - insulation
  - boundary
  - cooltools
requires:
  - cooler
  - cooltools
  - numpy
  - pandas
---

> **Status: implemented** (cooltools). Downstream Step 4b of the bulk Hi-C suite.

## When to use

The user has a balanced `.mcool` and wants TAD structure: a per-bin diamond
insulation score, boundary calls (local minima above a Li/Otsu-chosen prominence
threshold), and boundary strength. Mid-scale (~10–50 kb) 3D-genome layer.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-3 result | `<project>/matrix/result.json` (`matrix[].mcool`) | Yes |

| Output | Path | Notes |
|---|---|---|
| Insulation | `<output>/<sample>/*.insulation.*.tsv` (+ bigWig) | score + boundary flags per window |
| Boundaries | `<output>/<sample>/*.boundaries.*.bed` | called TAD boundaries (+ strength) |
| Result | `<output>/result.json` | `insulation[]` paths + boundary counts |

## Flow

1. Load Step-3 → `.mcool` paths.
2. Per sample: `cooltools insulation --threshold Li --view <main-chroms> <mcool::res> <window…>` (multi-window); extract boundary bins (primary window) → BED; build TAD domains (`extract_TADs`, weaker-boundary merge) → `*.TADs.*.bed`.
3. Write report / result.json / reproducibility / README.

## Gotchas

- **Resolution / window**: ~25 kb bins with a ~10× window (rule-of-thumb). Too-coarse bins blur boundaries; too-fine bins are noisy.
- **Threshold**: `Li`/`Otsu` auto-threshold boundary prominence; pass a float to fix it.
- **Graceful** — missing cooltools / failed call → empty result, not a crash.

## Key CLI

```bash
python skills/epigenomics/bulkhic/bulkhic-insulation/bulkhic-insulation.py \
    --prev-result ./hic_run/matrix/result.json --wd ./hic_run/insulation --resolution 25000
```

## See also

- `references/methodology.md` — diamond insulation score, boundary prominence.
- Upstream — `bulkhic-matrix`. Siblings — `bulkhic-compartments`, `bulkhic-loops`. Aggregate — `bulkhic-pileup`.
