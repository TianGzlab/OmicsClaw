---
name: sc-consensus-integration
description: Load when you want a multi-sample single-cell (scRNA) clustering robust to the choice of
  integration method — fanning out Harmony/Scanorama/scVI + an unintegrated baseline, scoring each by
  a batch-mixing intrinsic panel, and voting a consensus. Skip when single-batch (use sc-consensus-clustering);
  one integration method is fixed.
trigger: consensus integration, batch correction consensus, integration method consensus, robust scrna integration clustering, which clusters survive integration
tags:
- singlecell
- scrna
- consensus
- integration
- batch-correction
---

# sc-consensus-integration

## When to use

Verified consensus over **batch-correction representations**. For multi-sample
single-cell data the dominant axis of variation is not clustering resolution but
how batch effect is removed: clustering uncorrected PCA of multi-sample data
clusters *batches*, not cell types, and different integration methods
(Harmony / Scanorama / scVI / …) yield different embeddings and so different
clusterings. Use this when you have a preprocessed multi-sample AnnData with a
batch key in `obs` (≥2 batches) and want a clustering that is **not an artifact
of one integration method**, with per-cell confidence and batch-artifact flags.

It mirrors `consensus-domains`: members fan out `sc-integrate-cluster --method <m>`
— each a self-contained *integrate + cluster* unit — at a **fixed** resolution
(so member cluster counts stay comparable for the operator), scored by the
integration intrinsic panel before voting a consensus.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)
- Expects `obsm`: `X_pca`

**Outputs**

- `consensus_labels.tsv`
- `member_scores.csv`
- `member_intrinsic_panel.csv`
- `cross_method_nmi.csv`
- `plan.json`
- `report.md`
- `result.json`

## Flow

1. **Plan members** — the `--integration-methods` set (`none` baseline + harmony
   + scanorama by default; `scvi` via `--include-scvi`).
2. **Fan out** — run `sc-integrate-cluster --method <m>` per member at the fixed
   `--resolution` (member cluster counts stay comparable for the operator).
3. **Score** — the driver computes the **batch-mixing intrinsic panel** on each
   member's embedding + batch key. The single
   scored axis is `ilisi_norm` (iLISI diversity, `log(iLISI)/log(n_batches)`) —
   the one metric validated to track ground-truth cell-type recovery.
   `knn_preservation_norm` (within-batch `X_pca` retention), `batch_asw_norm` and
   `cluster_asw_norm` are reported as weight-0 **diagnostics** (`knn_preservation`
   anti-correlated with recovery, so it flags over-integration but does not score).
4. **Consensus** — vote `kmode` / `weighted` / `lca` over the **voting** members
   (the integration methods; the `none` baseline is excluded by default, B2).
5. **Report** — banner + per-cell support/entropy + a k-divergence section.

## Gotchas

- **`none` is the unintegrated `X_pca` baseline, and it does NOT vote by default**
  — it is a reference control that exposes batch-artifact clusters by comparison
  (it is scored, paneled and reported, with `selection_reason = "baseline …"`),
  but voting it as an equal drags the consensus toward un-integrated structure
  Pass `--vote-baseline` to include it in the vote.
- **scVI is GPU/stochastic and slow** — reproducible within tolerance, not
  bit-identical; add it with `--include-scvi` (which raises the per-member
  `--timeout` to 1800s, since scVI is ~10-15 min on ~15k cells) and serialise GPU
  members with `--max-parallel 1`. For very large datasets raise `--timeout`
  further. (If scVI is not installed the member fails with an import error, not a
  timeout — `pip install scvi-tools`.)
- **The intrinsic panel is unsupervised batch-mixing-vs-structure** — it is NOT
  validated against curated cell types; treat the score as a relative ranking and
  the panel weights in `plan.json` as experimental, not calibrated.
- **Fixed `--resolution` is intentional** — members must produce comparable
  cluster counts for the operator; do not sweep resolution here (use
  `sc-consensus-clustering` for the resolution-robustness question).

## Key CLI

```bash
# default members: unintegrated (X_pca baseline) + harmony + scanorama
python skills/singlecell/scrna/sc-consensus-integration/sc_consensus_integration.py \
  --input <preprocessed.h5ad> --output <dir> \
  --batch-key batch --resolution 1.0 --operator kmode --seed 0 --non-interactive

# add the GPU/stochastic scVI member (serialise GPU members)
python skills/singlecell/scrna/sc-consensus-integration/sc_consensus_integration.py --input <h5ad> --output <dir> \
  --include-scvi --max-parallel 1 --non-interactive

# explicit method set
python skills/singlecell/scrna/sc-consensus-integration/sc_consensus_integration.py --input <h5ad> --output <dir> \
  --integration-methods harmony,scanorama,scvi --non-interactive
```

## See also

- `references/methodology.md` — integration-consensus + intrinsic-panel rationale
- `references/output_contract.md` — `consensus_labels.tsv` / `member_scores.csv` / `plan.json` schema
- `references/parameters.md` — every CLI flag, per-method tunables
- Adjacent skills: `sc-preprocessing` (upstream), `sc-integrate-cluster` (the per-member integrate+cluster unit this wraps), `sc-consensus-clustering` (parallel — resolution-robustness instead of integration-robustness), `consensus-domains` (parallel — the spatial analogue)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `numpy`, `pandas`, `PyYAML`, `scanpy`, `scikit-learn`, `scipy`
