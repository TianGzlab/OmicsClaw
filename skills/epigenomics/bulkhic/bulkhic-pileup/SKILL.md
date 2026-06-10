---
name: bulkhic-pileup
description: "Load when aggregating Hi-C signal from a .mcool: coolpup.py stacks observed/expected snippets over loops (BEDPE, off-diagonal APA) or TAD domains (BED, size-rescaled 99x99) into a mean heatmap plus central-enrichment score. Features auto-discovered from sibling bulkhic-loops and bulkhic-tads runs; override with --features. Skip for ATAC/ChIP; needs bulkhic-loops/tads output first."
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
  - epigenomics
  - hi-c
  - pileup
  - apa
  - aggregate
  - cooltools
requires:
  - cooler
  - cooltools
  - numpy
  - pandas
  - matplotlib
---

> **Status: implemented** (cooltools). Downstream Step 4d of the bulk Hi-C suite.

## When to use

The user has a balanced `.mcool` and a feature set (loops or boundaries) and
wants an aggregate (pileup / APA-style) heatmap quantifying mean signal at those
features — e.g. "are these loops collectively strong?" or "how insulating are
these boundaries on average?". Typically run after `bulkhic-loops`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-3 result | `<project>/matrix/result.json` (`matrix[].mcool`) | Yes |
| Features | BEDPE (loops) or BED (boundaries) | `--features`, else **auto-discovered from BOTH sibling `loops/result.json` AND `insulation/result.json`** |

| Output | Path | Notes |
|---|---|---|
| Pileup | `<output>/<kind>/<sample>/*.pileup.*.npz` | aggregate O/E snippet stack (`<kind>` = loops / boundaries / custom) |
| Heatmap | `<output>/<kind>/<sample>/*.pileup.*.png` | APA-style mean heatmap |
| Result | `<output>/result.json` | `pileup[]` (each carries `kind`) + central-enrichment score |

## Flow

1. Load Step-3 → `.mcool` paths; discover feature sets: `--features` (one custom set), else BOTH siblings — loops BEDPE from `bulkhic-loops` (off-diagonal APA) **and** TAD domains BED from `bulkhic-tads` (on-diagonal, size-rescaled). Entries with 0 calls are skipped.
2. Per feature set × sample: `cooltools expected-cis` (O/E) → `coolpup.py … --expected … --clr_weight_name weight` (loops: `--flank`; TADs: `--local --rescale --rescale_flank 1.0 --rescale_size 99`) → `.clpy` in `<kind>/<sample>/`; render the mean heatmap + center enrichment.
3. Write report / result.json / reproducibility / README.

## Gotchas

- **Needs features** — either `--features` or a prior `bulkhic-loops` / `bulkhic-tads` run; with neither it degrades gracefully (empty result + guidance), it does not hard-fail.
- **Each feature kind goes in its own subdir** (`loops/`, `boundaries/`) so the per-sample `<sample>.pileup.<res>.npz` names never clash.
- **Resolution per feature kind** — by default each kind reuses the resolution it was called at (loops ~5–10 kb, boundaries ~10–25 kb); `--resolution` pins one for all sets.
- **Engine is `coolpup.py`** (coolpuppy); needs `setuptools<81` in the env (its `h5sparse` dep imports `pkg_resources`). Output is a `.clpy` file read via `coolpuppy.lib.io.load_pileup_df`.

## Key CLI

```bash
# Auto-discover BOTH loops (APA) and insulation boundaries from sibling runs
python skills/epigenomics/bulkhic/bulkhic-pileup/bulkhic-pileup.py \
    --prev-result ./hic_run/matrix/result.json --wd ./hic_run/pileup

# pin one resolution for all feature sets
python .../bulkhic-pileup.py --prev-result ./hic_run/matrix/result.json \
    --wd ./hic_run/pileup --resolution 10000

# override with a specific feature file (single custom set)
python .../bulkhic-pileup.py --prev-result ./hic_run/matrix/result.json \
    --wd ./hic_run/pileup --features ./hic_run/insulation/<s>/<s>.boundaries.25000.bed --features-format bed
```

## See also

- `references/methodology.md` — snippet stacking, expected normalisation, enrichment score.
- Upstream — `bulkhic-matrix` (+ `bulkhic-loops` / `bulkhic-tads` for features).
