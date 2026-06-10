---
name: bulkhic-loops
description: Load when calling chromatin loops from a balanced Hi-C .mcool — Mustache (scale-space blob detection) run independently at each resolution (default 5 kb + 10 kb), one BEDPE per resolution (no cross-resolution merge). Fine resolution (~5–10 kb). Skip for compartments (bulkhic-compartments) or TADs (bulkhic-tads); needs bulkhic-matrix output first.
version: 0.2.0
author: OmicsClaw
license: MIT
tags:
  - epigenomics
  - hi-c
  - loop
  - dots
  - hiccups
  - cooltools
requires:
  - mustache-hic   # dedicated env: omicsclaw_mustache (numpy<2)
  - cooler
  - numpy
  - pandas
---

> **Status: implemented** (Mustache). Downstream Step 4c of the bulk Hi-C suite.

## When to use

The user has a balanced `.mcool` and wants point-to-point chromatin loops —
focal contact enrichments (e.g. CTCF/cohesin loops). **Mustache** (scale-space
Laplacian-of-Gaussian blob detection) is the loop caller used by the production
pipeline. It is run independently at each requested resolution (default 5 kb +
10 kb); each resolution's loops are written as their own BEDPE — there is NO
cross-resolution merge. Mustache reads the `.mcool` directly.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-3 result | `<project>/matrix/result.json` (`matrix[].mcool`) | Yes |

| Output | Path | Notes |
|---|---|---|
| Loops | `<output>/<sample>/*.loops.<res>.bedpe` | one BEDPE per resolution (no merge) |
| Result | `<output>/result.json` | `loops[]` paths + counts + expected tsv |

## Flow

1. Load Step-3 → `.mcool` paths.
2. Per sample, per resolution: `mustache -f <mcool> -r <res> -pt <fdr> -d <max_dist>` → TSV → BEDPE. No merge across resolutions.
3. Write report / result.json / reproducibility / README.

## Gotchas

- **Resolution**: 5–10 kb. Coarser is too sparse to resolve dots; <4 kb is usually too noisy/sparse.
- **Empty loop set is valid** — shallow or small-genome libraries may yield few/no dots; that is reported, not an error.
- **Mustache runs in its own env** (`omicsclaw_mustache`, numpy<2) — it calls `np.nan_to_num(<sparse>, copy=False)` which numpy≥2 forbids; the loops skill invokes that env's `mustache` binary directly. Install via `0_setup_env_for_bulkhic.sh`.
- **`-pt` is a p-value threshold** (default 0.1; production used 0.01 on deep data). Shallow libraries yield few/no loops.

## Key CLI

```bash
python skills/epigenomics/bulkhic/bulkhic-loops/bulkhic-loops.py \
    --prev-result ./hic_run/matrix/result.json --wd ./hic_run/loops --resolutions 5000,10000
```

## See also

- `references/methodology.md` — dot kernels, per-distance FDR, clustering.
- Upstream — `bulkhic-matrix`. Aggregate/validate — `bulkhic-pileup` (APA on these loops). Siblings — `bulkhic-compartments`, `bulkhic-tads`.
