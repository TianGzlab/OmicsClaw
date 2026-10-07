---
name: sc-grn
description: Load when inferring TF → target gene regulatory networks on a normalised scRNA AnnData via
  pySCENIC (GRNBoost2 + cisTarget + AUCell) or correlation-based GRN fallback (when arboreto is unavailable,
  in --demo, or with --allow-simplified-grn). Skip when computing ligand-receptor cell-cell signalling
  (use sc-cell-communication); predicting genetic-KO effects (use sc-in-silico-perturbation).
trigger: grn, gene regulatory, scenic, pyscenic, regulon, transcription factor, grnboost
tags:
- singlecell
- scrna
- grn
- gene-regulatory-network
- scenic
- pyscenic
- grnboost2
- aucell
- cistarget
---

# sc-grn

## Use from a step

```python
grn = load_skill("sc-grn")
adata = read_input("expression.h5ad")
edges = grn.infer_adjacencies(adata, tfs=["SPI1", "IRF8", "STAT1"],
                              method="correlation", n_top=50)
regulons = grn.regulons_from_adjacencies(edges)
scores = grn.score_regulons(adata, regulons, method="mean")
write_output(edges, "tables/adjacencies.csv")
write_output(scores, "tables/mean_target_expression.csv")
```

Functions do not annotate the input automatically. The PBMC example in
`examples/example_step.py` uses caller-supplied TFs and explicitly labeled
mean-expression scores.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `infer_adjacencies(adata, *, tfs, method: str='grnboost2', layer: str | None=None, random_state: int=42, n_top: int=50, n_jobs: int=4) -> pd.DataFrame`

Return TF, target and importance columns using the caller's TF list.

grnboost2 retains the CLI's fallback to absolute Spearman correlation
when its backend fails or returns no edges. Correlation excludes supplied
TFs from candidate targets and keeps n_top targets per TF. No motif
validation occurs here; a warning and run_info report any fallback.

:param tfs: TF names; only names present in the selected matrix are used.
:param method: grnboost2 (default) or correlation.
:param layer: Explicit expression layer; None prefers counts, aligned raw, then X.
:param random_state: GRNBoost2 seed, default 42. Correlation is deterministic.
:param n_top: Correlation targets per TF, default 50.
:param n_jobs: GRNBoost2 workers, default 4.
:returns: A new DataFrame; input AnnData is not modified.
:raises ValueError: The method or budget is invalid, or no TF overlaps.

### `run_info(adjacencies: pd.DataFrame, *, keep: bool=True) -> dict`

Return an independent backend/fallback record; keep=False removes it from attrs.

### `prune_regulons(adjacencies: pd.DataFrame, *, database_glob: str, motif_annotations: str, n_top: int=50, rank_threshold: int=5000, auc_threshold: float=0.05, nes_threshold: float=3.0, n_jobs: int=4) -> list[dict]`

Return motif-pruned regulon dictionaries using the existing cisTarget bridge.

Requires pySCENIC and caller-provided databases and motif annotations.
Thresholds retain the CLI defaults: rank 5000, AUC 0.05, NES 3 and 50
targets. Backend and resource errors propagate; no data are downloaded.

### `regulons_from_adjacencies(adjacencies: pd.DataFrame, *, n_top: int=50) -> list[dict]`

Group the strongest edges per TF without motif validation; default 50 targets.

### `score_regulons(adata, regulons: list[dict], *, method: str='aucell', random_state: int=42, n_jobs: int=4) -> pd.DataFrame`

Return per-cell regulon scores without annotating the input.

aucell requires pySCENIC and ranks count-layer/aligned-raw/X expression.
mean averages each regulon's targets in X, matching the old simplified
CLI. It is not AUCell, an enrichment statistic, or motif validation.

:param method: aucell (default) or mean; no automatic scoring fallback.
:param random_state: AUCell seed, default 42; mean is deterministic.
:param n_jobs: AUCell workers, default 4.
:returns: DataFrame indexed by cell; attrs names the scoring_method and is_aucell.
:raises ValueError: The scoring method is unknown.
:raises ImportError: AUCell's optional backend is unavailable.

### `regulon_heatmap_figure(scores: pd.DataFrame, *, groups: pd.Series | None=None)`

Return a score heatmap, optionally averaged over aligned cell groups.

<!-- api:end -->

## Methods and parameters

`infer_adjacencies` defaults to GRNBoost2, with `random_state=42` and
`n_jobs=4`. Its legacy fallback is absolute Spearman correlation, retaining
`n_top=50` targets per TF. `run_info(edges)` records the actual method and
fallback reason, also emitted as a warning. `method="correlation"` runs directly without arboreto.

The simplified path now respects the caller's TF list. Correlation gives
co-expression candidates, not validated regulatory edges.
`regulons_from_adjacencies` only groups these candidates;
`prune_regulons` needs pySCENIC, caller-provided cisTarget databases and
motif annotations. It retains rank threshold 5000, AUC threshold 0.05 and
NES threshold 3; it does not download resources.

`score_regulons(method="aucell")` requires pySCENIC and uses seed 42.
`method="mean"` averages target expression in X, matching the old simplified
CLI. Mean expression is not AUCell and has no enrichment p-value.

## Gotchas

- Inference selects an explicit layer, else counts, aligned raw, then X.
  Mean scoring uses X; verify its normalization separately (`_api.py:15`, `_api.py:98`).
- `run_info` is stored in DataFrame attrs; CSV does not preserve attrs.
  Save the diagnostics separately when exporting edges (`_api.py:61`).
- GRNBoost2/backend failure can trigger correlation; inspect the record.
  The full pySCENIC path also needs external resources and was not validated
  merely by running the correlation example (`_api.py:68`).
- The CLI preserves legacy `grn_auc_matrix.csv` and `regulon_<TF>` names
  for compatibility even for mean scores. Check `result.json["data"]["scoring_method"]`.
- Correlation targets exclude the TFs supplied in the same call.
  No TF overlap raises an error in the API (`_api.py:15`).

## Inputs & Outputs

The API returns adjacency tables, regulon dictionaries, score tables and
Figures. The CLI writes `processed.h5ad`, `tables/grn_adjacencies.csv`,
`tables/grn_regulons.csv`, `tables/grn_regulon_targets.csv`,
`tables/grn_auc_matrix.csv`, `report.md` and `result.json`.
Plots and their figure-data manifests depend on available scores.

## Key CLI

```bash
python skills/singlecell/scrna/sc-grn/sc_grn.py --demo --output /tmp/sc_grn_demo
python skills/singlecell/scrna/sc-grn/sc_grn.py --input expression.h5ad --tf-list tfs.txt --allow-simplified-grn --output results/
python skills/singlecell/scrna/sc-grn/sc_grn.py --input expression.h5ad --tf-list tfs.txt --db '/refs/*.feather' --motif motifs.tbl --output results/
```

## Dependencies

`anndata`, `arboreto`, `dask`, `matplotlib`, `networkx`, `numpy`, `pandas`, `pyscenic`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`
