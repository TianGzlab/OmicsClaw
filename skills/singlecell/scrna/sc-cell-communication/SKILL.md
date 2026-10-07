---
name: sc-cell-communication
description: Load when computing cell-cell ligand-receptor communication on an annotated scRNA AnnData
  via builtin scorer, LIANA, CellPhoneDB, CellChat (R), or NicheNet (R). Skip when assigning cell-type
  labels (use sc-cell-annotation); transcription factor → target regulatory networks (use sc-grn).
trigger: cell communication, cell-cell communication, ligand receptor, cellchat, liana, cellphonedb, nichenet
tags:
- singlecell
- scrna
- cell-communication
- ligand-receptor
- liana
- cellphonedb
- cellchat
- nichenet
---

# sc-cell-communication

## When to use

The user has an annotated scRNA AnnData (cell-type labels in
`obs["cell_type"]` or another column passed via `--cell-type-key`) and
wants ligand-receptor / sender-receiver interaction tables and figures.
Five backends:

- `builtin` (default) — compact curated L-R set, heuristic score, no p-values.
- `liana` — Python LIANA rank aggregation (recommended general default).
- `cellphonedb` — official CellPhoneDB statistical workflow (human-only).
- `cellchat_r` — R-backed CellChat with pathway / centrality outputs.
- `nichenet_r` — R-backed NicheNet ligand prioritisation; needs explicit `--receiver` + `--senders` + `--condition-*` (human-only).

For TF → target gene regulatory networks use `sc-grn`. For cell-type
labelling use `sc-cell-annotation`.

## Use in an analysis step

Use `load_skill` from the notebook SDK; write returned objects with
`write_output`. This runnable example is also in `examples/example_step.py`.
The CLI remains available for standalone reports and galleries.

```python
# Rank curated ligand-receptor mean products across PBMC clusters.
# Reads pbmc3k_processed and uses its log-normalized raw snapshot.
# Calls sc-cell-communication: communicate, sender_receiver_summary, interaction_heatmap_figure.
# The builtin method does not test statistical significance.

from skills._sdk.notebook import load_demo, load_skill, write_output

communication = load_skill('sc-cell-communication')
adata = load_demo('pbmc3k_processed').raw.to_adata()

table = communication.communicate(adata, cell_type_key='louvain')
write_output(table, 'tables/lr_interactions.csv')
write_output(communication.sender_receiver_summary(table), 'tables/sender_receiver.csv')
write_output(communication.interaction_heatmap_figure(table), 'figures/interaction_heatmap.png')

assert not table.empty
assert table.pvalue.isna().all()
assert (table.score > 0).all()
assert set(table.source).issubset(set(adata.obs['louvain'].astype(str)))
```

## Inputs & Outputs

Input is an annotated AnnData. builtin, LIANA, CellPhoneDB and CellChat
use normalized X; NicheNet needs count-like data. PCA and neighbors are
not required. The API returns an interaction DataFrame, with backend
diagnostics and optional tables accessible through helpers.

The CLI writes `processed.h5ad`, `report.md`, `result.json`, and
`tables/lr_interactions.csv`, `top_interactions.csv`,
`sender_receiver_summary.csv`, `group_role_summary.csv`,
`pathway_summary.csv`. CellChat can add pathway, centrality, count and
weight tables; CellPhoneDB can add means, p-values and significant means;
NicheNet can add ligand activities and target links. Those tables and the
corresponding figures are conditional. Backend exchange files are temporary.

## Flow

1. Load AnnData; preflight `--cell-type-key`, species, and per-method requirements (e.g., NicheNet needs `--receiver` / `--senders` / `--condition-*`).
2. Dispatch via `communicate` to the chosen backend (one of `builtin` / `liana` / `cellphonedb` / `cellchat_r` / `nichenet_r`).
3. Standardise the L-R table to columns `ligand`, `receptor`, `source`, `target`, `score`, `pvalue`, `pathway`.
4. Build sender-receiver / role / pathway summaries.
5. Detect "no interactions found" and print a UX-guardrail message; do NOT raise.
6. Save tables, figures, `processed.h5ad`, `report.md`, `result.json` (incl. `score_semantics` / `significance_semantics` / `pvalue_available`).

## Gotchas

- `run_info(table)["fallback_used"]` is false: a missing selected backend raises; the API does not silently switch to builtin.
- builtin scores are grouped ligand mean × receptor mean, not interaction probabilities. `pvalue` is NaN and `n_significant` is zero.
- LIANA's `specificity_rank` is a consensus rank, not a p-value. `tables/lr_interactions.csv` retains that column, leaves `pvalue` NaN and reports zero significant interactions. Its default seed is 1337; the wrapper retains its existing species-independent resource selection.
- CellPhoneDB is human-only and now passes seed 0 to `debug_seed`. `cellphonedb_lr(random_state=...)` changes it. Its v4.1.0 database downloads on first use to the user's cache; this is not an offline path unless cached.
- CellChat and NicheNet need their R dependency stacks. NicheNet is human-only and also requires `lr_network_human_21122021.rds` and `weighted_networks_nsga2r_final.rds` under the user's `.cache/omicsclaw/nichenet/`; the wrapper does not download them.
- Empty interaction tables are valid output. Check `run_info(table)["n_interactions_tested"]` before plotting or interpreting them.

## Key CLI

```bash
# Demo (built-in annotated PBMC)
python skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py --demo --output /tmp/sc_ccc_demo

# Default builtin scorer (heuristic, no pvalue)
python skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py \
  --input annotated.h5ad --output results/

# LIANA rank aggregation (recommended general default)
python skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py \
  --input annotated.h5ad --output results/ --method liana

# CellPhoneDB statistical (human only)
python skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py \
  --input annotated.h5ad --output results/ \
  --method cellphonedb --cellphonedb-iterations 1000 --cellphonedb-threshold 0.1

# CellChat R workflow
python skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py \
  --input annotated.h5ad --output results/ \
  --method cellchat_r --cellchat-prob-type triMean

# NicheNet ligand prioritisation across conditions (human only)
python skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py \
  --input annotated.h5ad --output results/ \
  --method nichenet_r \
  --condition-key condition --condition-oi stim --condition-ref ctrl \
  --receiver "Monocyte" --senders "T_cell,B_cell" --nichenet-top-ligands 20
```

## See also

- `references/parameters.md` — every CLI flag, per-backend tunables
- `references/methodology.md` — when each backend wins; species coverage
- `references/output_contract.md` — `lr_interactions.csv` columns + `result.json` keys per backend
- Adjacent skills: `sc-cell-annotation` (upstream — produces `obs["cell_type"]`), `sc-clustering` (upstream — provides leiden/louvain if you pass `--cell-type-key leiden`), `sc-grn` (parallel — TF→target regulatory networks, NOT L-R), `sc-differential-abundance` (parallel — cross-condition cell-state proportion changes)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `cellphonedb`, `liana`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `communicate(adata, *, method: str='builtin', cell_type_key: str='cell_type', species: str='human', cellphonedb_counts_data: str='hgnc_symbol', cellphonedb_iterations: int=1000, cellphonedb_threshold: float=0.1, cellphonedb_threads: int=4, cellphonedb_pvalue: float=0.05, cellchat_prob_type: str='triMean', cellchat_min_cells: int=10, condition_key: str | None=None, condition_oi: str | None=None, condition_ref: str | None=None, receiver: str | None=None, senders: list[str] | None=None, nichenet_top_ligands: int=20, nichenet_expression_pct: float=0.1, nichenet_lfc_cutoff: float=0.25, liana_random_state: int=1337, cellphonedb_random_state: int=0) -> pd.DataFrame`

Return ranked ligand-receptor interactions without changing the input.

builtin multiplies grouped ligand and receptor means and supplies no
p-values. LIANA retains specificity_rank as a rank, not a significance
statistic, and ignores species as in the existing wrapper. CellPhoneDB
uses debug_seed=0 by default; its database may download on first use.
R methods use temporary H5AD exchange files. NicheNet needs its two
local resource files. Optional backend imports occur only when selected.
Backend-specific tables and diagnostics are accessible through helpers.

### `builtin_lr(adata, *, cell_type_key: str='cell_type', species: str='human') -> pd.DataFrame`

Return the curated mean-product heuristic; pvalue is always NaN.

### `liana_lr(adata, *, cell_type_key: str='cell_type', species: str='human', random_state: int=1337) -> pd.DataFrame`

Return LIANA consensus scores and specificity ranks; neither is a p-value.

### `cellphonedb_lr(adata, *, cell_type_key: str='cell_type', species: str='human', counts_data: str='hgnc_symbol', iterations: int=1000, threshold: float=0.1, threads: int=4, pvalue: float=0.05, random_state: int=0) -> pd.DataFrame`

Run CellPhoneDB permutations with an explicit debug_seed; database may download.

### `cellchat_lr(adata, *, cell_type_key: str='cell_type', species: str='human', prob_type: str='triMean', min_cells: int=10) -> pd.DataFrame`

Run CellChat in R on normalized X; require the existing R dependency stack.

### `nichenet_ligands(adata, *, cell_type_key: str='cell_type', species: str='human', condition_key: str, condition_oi: str, condition_ref: str, receiver: str, senders: list[str], top_ligands: int=20, expression_pct: float=0.1, lfc_cutoff: float=0.25) -> pd.DataFrame`

Run NicheNet and return LR scores; backend_tables includes ligand activities.

### `sender_receiver_summary(table: pd.DataFrame) -> pd.DataFrame`

Return mean scores and interaction counts for each sender-receiver pair.

### `group_role_summary(table: pd.DataFrame) -> pd.DataFrame`

Return summed incoming and outgoing interaction scores for each cell type.

### `pathway_summary(table: pd.DataFrame, *, pathways: pd.DataFrame | None=None) -> pd.DataFrame`

Return mean pathway scores, using CellChat pathway results when supplied.

### `top_interactions(table: pd.DataFrame, *, n: int=50) -> pd.DataFrame`

Return the first n interactions in the backend's existing ranked order.

### `backend_tables(table: pd.DataFrame) -> dict[str, pd.DataFrame]`

Return copies of backend-specific tables, including optional R summaries.

### `interaction_heatmap_figure(table: pd.DataFrame)`

Return a sender-by-receiver mean-score heatmap without writing files.

### `run_info(table: pd.DataFrame) -> dict`

Return backend provenance and significance semantics without result tables.

<!-- api:end -->
