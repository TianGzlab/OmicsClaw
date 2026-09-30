---
name: sc-velocity
description: Load when computing RNA velocity vectors on a scRNA AnnData with spliced / unspliced layers
  via scVelo (stochastic / dynamical / steady-state); dynamical mode additionally exports latent time.
  Skip when input lacks spliced+unspliced layers (use sc-velocity-prep); trajectory pseudotime ordering
  (use sc-pseudotime).
trigger: rna velocity, velocity, scvelo, spliced unspliced, cellular dynamics, velovi, velocity pseudotime
tags:
- singlecell
- scrna
- velocity
- rna-velocity
- scvelo
- latent-time
- kinetics
---

# sc-velocity

## When to use

The user has a scRNA AnnData with `layers["spliced"]` and
`layers["unspliced"]` already populated (typically from
`sc-velocity-prep` running `velocyto` / `STARsolo` / `kb-python`) and
wants per-cell velocity vectors, magnitude maps, and optional latent
time. Three scVelo modes:

- `scvelo_stochastic` (default) — fast, robust to noise.
- `scvelo_dynamical` — full splicing-kinetics model + latent time
  (slower, more interpretable).
- `scvelo_steady_state` — simplest approximation, fastest.

For ordering cells along a trajectory without splicing kinetics use
`sc-pseudotime`. To **generate** the spliced/unspliced layers from raw
FASTQs / cellranger output, run `sc-velocity-prep` first.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/cell_metadata.csv`
- `tables/top_velocity_genes.csv`
- `tables/velocity_cells.csv`
- `tables/velocity_summary.csv`
- `figures/latent_time_distribution.png`
- `figures/latent_time_umap.png`
- `figures/r_embedding_discrete.png`
- `figures/r_embedding_feature.png`
- `figures/r_velocity.png`
- `figures/velocity_magnitude_distribution.png`
- `figures/velocity_magnitude_umap.png`
- `figures/velocity_stream.png`
- `figures/velocity_top_genes.png`
- `adata_with_velocity.h5ad`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `layers`: `velocity`
- When `--method` is `scvelo_dynamical`:
  - AnnData additionally guarantees `obs`: `latent_time`
  - Produces artifact `singlecell.latent_time` as `processed.h5ad` (`h5ad`)

## Flow

1. Load AnnData (`--input`) or build a synthetic demo with spliced / unspliced layers.
2. Preflight `requires_layers=("spliced", "unspliced")` for the chosen method.
3. Run scVelo: filter & normalise → moments → velocity (mode-specific) → velocity graph.
4. If `scvelo_dynamical`: also compute latent time and gene-level dynamics.
5. Detect degenerate output (zero velocity genes / all-NaN) and emit a multi-action fix message in `result.json["suggested_actions"]` — does NOT raise.
6. Render figures, write tables, save `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **Missing `spliced` / `unspliced` layers fail at preflight.** The METHOD_REGISTRY entries at `sc_velocity.py` declare `requires_layers=("spliced", "unspliced")`; the shared preflight aborts before scVelo runs. Generate the layers with `sc-velocity-prep` (`--method velocyto`, `starsolo`, or `kb-python`) first.
- **Degenerate velocity is a soft fail, not an exception.** When scVelo can't fit a meaningful kinetics model, `sc_velocity.py` records `result.json["degenerate"]=True`, `n_velocity_genes=0`, `all_zero_velocity=True` and writes `suggested_actions: [...]` — but the script returns 0. Always check `result.json["n_velocity_genes"]` before consuming the `velocity` layer downstream (e.g., before passing to `sc-pseudotime --method cellrank --cellrank-use-velocity`).
- **`--method` accepts both METHOD_REGISTRY names and `_MODE_ALIAS_MAP` keys.** `sc_velocity.py` builds `choices` as the union — passing a legacy alias (e.g., `--mode stochastic`) silently maps to `scvelo_stochastic`. The actual mode used is recorded in `result.json["mode"]`.
- **`scvelo_dynamical` is the only mode that produces `latent_time`.** `sc_velocity.py` writes `result.json["latent_time_range"]` only when `obs["latent_time"]` is populated. Stochastic / steady-state modes return velocity but no latent time — `figures/latent_time_umap.png` won't be written.
- **`--input` is mandatory unless `--demo` (parser.error, exit code 2).** `sc_velocity.py` calls `parser.error("--input required when not using --demo")`. Once `--input` is provided, `main` raises `FileNotFoundError(f"Input file not found: {input_path}")` for a bad path.
- **All scVelo backends require the `scvelo` Python package.** All 3 METHOD_REGISTRY entries declare `dependencies=("scvelo",)`. The shared dependency manager raises `ImportError` if scvelo isn't installed.

## Key CLI

```bash
# Demo (synthetic spliced/unspliced)
python skills/singlecell/scrna/sc-velocity/sc_velocity.py --demo --output /tmp/sc_velocity_demo

# Default stochastic on real velocity-prepped data
python skills/singlecell/scrna/sc-velocity/sc_velocity.py \
  --input velocity_ready.h5ad --output results/

# Dynamical (full kinetics + latent time)
python skills/singlecell/scrna/sc-velocity/sc_velocity.py \
  --input velocity_ready.h5ad --output results/ \
  --method scvelo_dynamical --n-jobs 8

# Steady-state (fastest approximation)
python skills/singlecell/scrna/sc-velocity/sc_velocity.py \
  --input velocity_ready.h5ad --output results/ \
  --method scvelo_steady_state
```

## See also

- `references/parameters.md` — every CLI flag, per-mode notes
- `references/methodology.md` — when each scVelo mode wins; degenerate-output checklist
- `references/output_contract.md` — `layers["velocity"]` / `obs["latent_time"]` schema
- Adjacent skills: `sc-velocity-prep` (upstream — produces `layers["spliced"]` / `layers["unspliced"]`), `sc-pseudotime` (parallel — graph-based trajectory ordering, can consume velocity via `--cellrank-use-velocity`), `sc-clustering` (upstream — provides `obsm["X_umap"]` for the stream plot)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `cellrank`, `matplotlib`, `numpy`, `palantir`, `pandas`, `pyVIA`, `scanpy`, `scikit-learn`, `scipy`, `scvelo`, `seaborn`
