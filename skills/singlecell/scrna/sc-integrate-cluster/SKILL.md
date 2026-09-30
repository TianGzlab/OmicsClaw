---
name: sc-integrate-cluster
description: Load when running a single batch-correction representation (none/Harmony/Scanorama/scVI)
  + clustering of single-cell data as one self-contained unit — normally fanned out as a member of sc-consensus-integration.
  Skip when you want the full integration consensus (use sc-consensus-integration); resolution-robust
  clustering (use sc-consensus-clustering).
tags:
- singlecell
- scrna
- integration
- clustering
- consensus
---

# sc-integrate-cluster

**Domain:** Single-Cell Omics (scRNA) · **Role:** consensus member skill

## When to use

One self-contained *integrate + cluster* unit, used as a fan-out member of
`sc-consensus-integration`. It produces a batch-correction
representation **and** clusters on it at a fixed resolution, emitting the standard
`sc-clustering` artifact schema so the consensus `ScClusteringArtifactReader`
reads it unchanged. You normally do **not** call this directly — the consensus
planner fans it out across methods. Input is a preprocessed AnnData with an `obs`
batch key (≥2 batches for any real integration method); an `X_pca` baseline is
computed if absent.

This is the single-cell analog of `spatial-domains --method <m>`: the integration
consensus fans out genuinely different batch-correction representations.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `figure_data/embedding_points.csv`
- `figure_data/clustering_summary.csv`
- `processed.h5ad`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obsm`: `X_pca`

## Flow

1. Load the preprocessed AnnData; compute an `X_pca` baseline if absent.
2. Run the `--method` backend to produce `obsm[representation_used]`
   (`X_pca` for `none`).
3. Build the neighbour graph on that representation and cluster with
   `--cluster-method` at the fixed `--resolution`.
4. Write `figure_data/embedding_points.csv` + `figure_data/clustering_summary.csv`
   + `processed.h5ad` + `result.json`.

## Gotchas

- **`processed.h5ad` carries the member's integrated embedding** — the consensus
  driver reads `obsm[representation_used]` from it to compute the integration
  intrinsic panel. Do not strip obsm keys before the driver runs.
- **`result.json["representation_used"]` records which embedding was used** —
  `X_pca` for `--method none`, `X_<method>` otherwise; the consensus reader keys
  off this rather than re-deriving it.
- **Fixed `--resolution` is by design** — members must produce comparable cluster
  counts for the consensus operator; sweeping resolution belongs in
  `sc-consensus-clustering`, not here.
- **scVI is GPU/stochastic** — reproducible within tolerance, not bit-identical;
  serialise GPU members (`--max-parallel 1` at the consensus level).

## Key CLI

```bash
# Synthetic smoke demo (no input needed)
python skills/singlecell/scrna/sc-integrate-cluster/sc_integrate_cluster.py --demo --output /tmp/sic_demo

python skills/singlecell/scrna/sc-integrate-cluster/sc_integrate_cluster.py \
  --input <preprocessed.h5ad> --output <member_dir> \
  --method harmony --batch-key batch --resolution 1.0 --cluster-method leiden --seed 0
```

## See also

- `references/methodology.md` — integrate-then-cluster member rationale
- `references/output_contract.md` — the `figure_data/` schema the consensus reads
- `references/parameters.md` — every CLI flag, per-method tunables
- Adjacent skills: `sc-preprocessing` (upstream), `sc-consensus-integration` (the consensus that fans this out), `sc-clustering` (the non-integration single-resolution clusterer)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `harmonypy`, `matplotlib`, `numpy`, `pandas`, `scanorama`, `scanpy`, `scikit-learn`, `scvi-tools`, `seaborn`, `torch`
