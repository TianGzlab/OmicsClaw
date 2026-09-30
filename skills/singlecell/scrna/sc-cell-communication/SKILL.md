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

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/_matrix.csv`
- `tables/cellchat_centrality.csv`
- `tables/cellchat_count_matrix.csv`
- `tables/cellchat_pathways.csv`
- `tables/cellchat_results.csv`
- `tables/cellchat_weight_matrix.csv`
- `tables/cellphonedb_means.csv`
- `tables/cellphonedb_pvalues.csv`
- `tables/cellphonedb_significant_means.csv`
- `tables/group_role_summary.csv`
- `tables/lr_interactions.csv`
- `tables/meta.tsv`
- `tables/nichenet_ligand_activities.csv`
- `tables/nichenet_ligand_receptors.csv`
- `tables/nichenet_ligand_target_links.csv`
- `tables/nichenet_lr_network.csv`
- `tables/pathway_summary.csv`
- `tables/sender_receiver_summary.csv`
- `tables/top_interactions.csv`
- `figures/r_ccc_bipartite.png`
- `figures/r_ccc_bubble.png`
- `figures/r_ccc_diff_network.png`
- `figures/r_ccc_heatmap.png`
- `figures/r_ccc_network.png`
- `figures/r_ccc_stat_bar.png`
- `figures/r_ccc_stat_scatter.png`
- `figures/r_ccc_stat_violin.png`
- `input.h5ad`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`)

## Flow

1. Load AnnData; preflight `--cell-type-key`, species, and per-method requirements (e.g., NicheNet needs `--receiver` / `--senders` / `--condition-*`).
2. Dispatch via `run_communication` to the chosen backend (one of `builtin` / `liana` / `cellphonedb` / `cellchat_r` / `nichenet_r`).
3. Standardise the L-R table to columns `ligand`, `receptor`, `source`, `target`, `score`, `pvalue`, `pathway`.
4. Build sender-receiver / role / pathway summaries.
5. Detect "no interactions found" and print a UX-guardrail message; do NOT raise.
6. Save tables, figures, `processed.h5ad`, `report.md`, `result.json` (incl. `score_semantics` / `significance_semantics` / `pvalue_available`).

## Gotchas

- **No silent fallback to `builtin` when a backend is missing.** `sc_cell_communication.py` raises `ImportError` if `liana` is unavailable; raises for `cellphonedb`; raises for missing `cellchat_r` / `nichenet_r` R packages. `result.json["fallback_used"]` is always `False` — vestigial field, ignore it.
- **`cellphonedb` is human-only.** `sc_cell_communication.py` raises `ValueError("The current CellPhoneDB wrapper only supports species='human'.")`. Mouse data must use `liana` / `cellchat_r` / `builtin`.
- **`nichenet_r` is human-only and requires explicit receiver / senders.** `sc_cell_communication.py` raises `ValueError("The current NicheNet wrapper only supports species='human'.")`. The runner needs `--receiver <single>`, `--senders <comma-list>`, `--condition-key`, `--condition-oi`, `--condition-ref` to score ligand activity at the receiver between conditions.
- **CellPhoneDB DB cache must exist.** `sc_cell_communication.py` raises `FileNotFoundError(f"CellPhoneDB database not found at {db_path}")`. The cache lives at `~/.cache/omicsclaw/cellphonedb/<version>/cellphonedb.zip` — the wrapper expects it pre-populated.
- **`builtin` has no significance test — `pvalue` column is empty.** `sc_cell_communication.py` sets `result.json["pvalue_available"] = False` and `n_significant = 0`. The `score` is `ligand_mean × receptor_mean` heuristic — don't quote it as a formal interaction probability.
- **Empty interactions only print a warning, do not raise.** `main` detects zero interactions, prints a multi-option fix message, but the pipeline still writes empty `tables/lr_interactions.csv` and exits 0. Always check `result.json["n_interactions_tested"]` before consuming downstream.
- **`--cell-type-key` must already exist in `obs`.** `sc_cell_communication.py` raises `ValueError(f"Cell type key '{cell_type_key}' not in adata.obs: ...")`. Run `sc-cell-annotation` first if `obs["cell_type"]` is absent, or pass `--cell-type-key leiden`.
- **`--input` mandatory without `--demo`.** `sc_cell_communication.py` raises `ValueError("--input required when not using --demo")`.

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
