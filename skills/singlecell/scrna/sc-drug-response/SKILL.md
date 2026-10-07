---
name: sc-drug-response
description: Load when scoring drug sensitivity per cluster on an annotated scRNA AnnData via simple-correlation
  against drug-target signatures or via CaDRReS-Sc pretrained models (GDSC / PRISM). Skip when the AnnData
  has no cluster labels yet (use sc-clustering); predicting genetic-perturbation effects (use sc-in-silico-perturbation).
tags:
- singlecell
- scrna
- drug-response
- pharmacogenomics
- cadrres
- gdsc
- prism
---

# sc-drug-response

Summarize drug-associated gene expression or apply supplied CaDRReS models.
The default does not predict drug sensitivity or recommend treatment.

## Key CLI

```bash
python skills/singlecell/scrna/sc-drug-response/sc_drug_response.py --demo --output /tmp/sc_drug_demo
python skills/singlecell/scrna/sc-drug-response/sc_drug_response.py --input clustered.h5ad --cluster-key leiden --output results/drug_expression
python skills/singlecell/scrna/sc-drug-response/sc_drug_response.py --input clustered.h5ad --cluster-key leiden --method cadrres --drug-db gdsc --model-dir /path/to/trusted/models --output results/cadrres
```

## Methods and Workflow

`simple_correlation` is a legacy CLI name for mean expression, not correlation.
It averages available genes in each drug-associated gene set and cell group,
reports `mean_target_expression`, and ranks those descriptive means. Built-in
sets include targets, resistance and response-associated genes with no signed
weights. More expression does not imply more sensitivity or clinical benefit.

`cadrres` requires the omicverse adapter, a local CaDRReS-Sc checkout and trusted
pretrained model files. No models are bundled or downloaded. The old release
download links are unavailable; no replacement source is claimed here. Returned
`Score` is model output: inspect its units and direction, not just rank.

Upstream: `sc-preprocessing` and cluster/cell-type annotation. Downstream:
inspect gene overlap and expression patterns before any experimental follow-up.

## Inputs & Outputs

Input: normalized expression in `.h5ad` with gene symbols and a group column.
PCA/neighbours are not required for scoring. The CLI writes `processed.h5ad`,
`tables/drug_rankings.csv`, `report.md`, `result.json` and
`reproducibility/commands.sh`. Bar/heatmap figures are written when scores are
available; `figures/drug_sensitivity_umap.png` is a legacy filename and requires
UMAP. `obs['drug_score_<drug>']` are legacy names for the same group-level values,
not per-cell response predictions. Temporary CaDRReS CSV files are not public outputs.

## Gotchas

- `tables/drug_rankings.csv` has `mean_target_expression` for the default and `Score` for CaDRReS. Do not compare their units.
- `result.json` → `summary.n_drugs_scored` is zero if no gene set overlaps; review `TargetGenes`, `TotalTargets` and `OverlapPct` in the table.
- Pass `--cluster-key` on real data; automatic selection can choose an unintended categorical column. The API accepts `cluster_key=None` to summarize all cells.
- `--method cadrres --demo` generates explicitly synthetic plumbing scores without a real model. The API never substitutes synthetic predictions for a missing model.
- `report.md` includes the SDK's OmicsClaw research-use disclaimer unchanged.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `score_drug_targets(adata, *, cluster_key=None, drug_targets=None)`

Return mean_target_expression for each drug-associated gene set and group.

Averages X over available genes and cells, rounding to four decimals to
preserve the CLI table. No model is fitted; this is neither correlation nor
drug sensitivity, and high expression does not establish benefit. Pass
normalized expression and a group key; None summarizes all cells together.

### `builtin_drug_targets()`

Return a copy of 15 illustrative drug-associated gene sets.

These include targets, resistance and response-associated genes without
direction or potency weights. They are not a validated response signature.

### `cadrres(adata, *, cluster_key, model_dir, drug_db='gdsc', n_drugs=10)`

Return CaDRReS model scores using explicitly supplied trusted local models.

Requires omicverse's Drug_Response adapter and a CaDRReS-Sc checkout beside
model_dir or under the home directory. Models are not bundled or downloaded;
upstream download locations have not been validated. Temporary predictions
do not modify model_dir. Score units and direction depend on the model.

### `run_info(table)`

Return score-column and interpretation metadata from a result table.

### `top_drugs(table, *, n_top=10)`

Return drug means across groups, ordered by decreasing descriptive/model score.

Ranking model scores this way preserves the CLI order, not clinical benefit.

### `top_drugs_figure(table, *, n_top=10)`

Return a Figure labelled with expression or model-score units, without saving.

<!-- api:end -->

## Dependencies

`anndata`, `matplotlib`, `numpy`, `omicverse`, `pandas`, `scanpy`, `scipy`, `seaborn`

omicverse is needed only for the model-backed method. The default and notebook
example use local expression means without CaDRReS.
