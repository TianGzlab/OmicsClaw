---
name: spatial-velocity
description: Load when estimating RNA velocity on a spatial AnnData with `layers["spliced"]` + `layers["unspliced"]` via scVelo (stochastic / deterministic / dynamical) or veloVI (deep generative). Skip when input lacks the spliced/unspliced layers (must be quantified upstream by velocyto / kb-python / STARsolo) or for non-spatial scRNA velocity (use `sc-velocity`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- spatial
- velocity
- rna-velocity
- scvelo
- velovi
- dynamics
requires:
- anndata
- scanpy
- scvelo
- numpy
- pandas
---

# spatial-velocity

## When to use

The user has a spatial AnnData with `layers["spliced"]` and
`layers["unspliced"]` populated upstream (velocyto / kb-python /
STARsolo) and wants RNA velocity estimated, with PAGA + cluster
summaries and stream / phase / spatial plots. Four backends:

- `stochastic` (default scVelo) — moment-based, fast.
- `deterministic` (scVelo) — least-squares fit, no stochastic
  correction.
- `dynamical` (scVelo) — full latent-time inference via
  `recover_dynamics`. Slow on > 5K cells; use `--dynamical-n-jobs`.
- `velovi` — deep generative model with latent time. Tunables
  `--velovi-n-hidden`, `--velovi-n-latent`, `--velovi-n-layers`.

Cluster column defaults to `leiden` (`--cluster-key`). For
trajectory inference without spliced layers use `spatial-trajectory`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Spatial AnnData with spliced/unspliced layers | `.h5ad` with `layers["spliced"]`, `layers["unspliced"]`, `obsm["spatial"]`, `obs[cluster_key]` (default `leiden`) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | `layers["velocity"]` (every method); `layers["latent_time_velovi"]` + `layers["fit_t"]` (velovi only); `obs["velocity_speed"]`, `obs["latent_time"]` (velovi); `var["fit_scaling"]`, `var["velocity_genes"]`, `var["fit_t_"]` (dynamical) |
| Cell-level metrics | `tables/cell_velocity_metrics.csv` | per-cell speed / coherence |
| Gene-level summary | `tables/gene_velocity_summary.csv` | per-gene fit stats |
| Velocity-gene hits | `tables/velocity_gene_hits.csv` | gene filter (R² + likelihood) |
| Cluster summary | `tables/velocity_cluster_summary.csv` | per-cluster mean speed |
| Top cells / genes | `tables/top_velocity_cells.csv`, `tables/top_velocity_genes.csv` | ranked summaries |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData; verify `layers["spliced"]` + `layers["unspliced"]` (`_lib/velocity.py:93-100` raises `ValueError` if missing). For `--demo`, `add_demo_velocity_layers` synthesises them (`spatial_velocity.py:1556`).
2. Common preprocessing: `velocity_min_shared_counts` filter → HVG cap → PCA → neighbours → moments.
3. For scVelo (`stochastic`/`deterministic`/`dynamical`): compute velocity, velocity graph; `dynamical` runs `recover_dynamics` first.
4. For `velovi`: train deep generative model; write per-cell `obs["latent_time"]` (`_lib/velocity.py:551`) and `obs["velocity_speed"]` (`_lib/velocity.py:215`).
5. Compute PAGA + cluster-mean speed; render stream / phase / heatmap / spatial / PAGA plots.
6. Save tables + `processed.h5ad` + report.

## Gotchas

- **`layers["spliced"]` + `layers["unspliced"]` REQUIRED.** `_lib/velocity.py:93-100` raises `ValueError` if either is missing — there is no auto-fallback. Real data needs upstream velocyto / kb-python / STARsolo. `--demo` synthesises layers via `add_demo_velocity_layers` (`_lib/velocity.py:106-121`); demo-synthetic velocities are for CI only, NOT biological inference.
- **`dynamical` is much slower than `stochastic`.** `recover_dynamics` is per-gene NB optimisation; expect minutes-to-hours on > 5K cells. Use `--dynamical-n-jobs N` and consider `--dynamical-n-top-genes` to cap the fit set.
- **velovi writes its own latent time, NOT scVelo's.** Inside the velovi branch (`_lib/velocity.py:468-571`), `:548-551` writes `layers["velocity"]`, `layers["latent_time_velovi"]`, `layers["fit_t"]`, and `obs["latent_time"]` (per-cell mean of `layers["latent_time_velovi"]`); `:567` writes `var["fit_t_"]` (velovi switch-time). The scVelo `dynamical` path runs `scv.tl.recover_dynamics` (`_lib/velocity.py:384`) — it writes scVelo's own `var["fit_*"]` family via the library, but does NOT write `layers["latent_time_velovi"]` or `obs["latent_time"]`.
- **`obs["velocity_speed"]` is computed for every method.** `_lib/velocity.py:207` (cluster-mean variant) and `_lib/velocity.py:215` always populate it — scVelo computes from velocity graph; velovi from latent-time gradient.
- **Cluster key default is `leiden`.** `spatial_velocity.py:1569` defaults `--cluster-key` to `"leiden"`. If your annotation column is named differently, pass `--cluster-key cell_type` or PAGA / cluster summaries will mis-bin.
- **`var["velocity_genes"]` semantics differ per backend.** Velovi sets it unconditionally to `True` for every gene (`_lib/velocity.py:553`). scVelo (`stochastic` / `deterministic` / `dynamical`) populates it as a real boolean filter inside `scv.tl.velocity` (`_lib/velocity.py:395`) using `min_r2` + `min_likelihood`. Always cross-check against `tables/velocity_gene_hits.csv` (the canonical filtered hit list) before reading `var["velocity_genes"]`.

## Key CLI

```bash
# Demo (synthetic spliced/unspliced)
python omicsclaw.py run spatial-velocity --demo --output /tmp/velo_demo

# scVelo stochastic (default)
python omicsclaw.py run spatial-velocity \
  --input data_with_spliced.h5ad --output results/ \
  --method stochastic --cluster-key leiden \
  --velocity-min-shared-counts 30 --velocity-n-top-genes 2000

# scVelo dynamical (full latent-time inference)
python omicsclaw.py run spatial-velocity \
  --input data_with_spliced.h5ad --output results/ \
  --method dynamical --dynamical-max-iter 10 --dynamical-n-jobs 4

# veloVI (deep generative)
python omicsclaw.py run spatial-velocity \
  --input data_with_spliced.h5ad --output results/ \
  --method velovi --velovi-n-hidden 256 --velovi-n-latent 10
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins
- `references/output_contract.md` — `layers` / `obs` / `var` keys per method
- Adjacent skills: `sc-velocity-prep` (upstream singlecell — quantifies spliced/unspliced from BAMs; same approach needed for spatial), `spatial-trajectory` (parallel — pseudotime without spliced layers), `sc-velocity` (parallel — non-spatial), `spatial-domains` (upstream — provides `obs["leiden"]`)
