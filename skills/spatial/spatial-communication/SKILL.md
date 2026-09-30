---
name: spatial-communication
description: Load when computing ligand-receptor cell-cell communication on a preprocessed spatial AnnData
  with `obs[cell_type_key]` (default `leiden`) via LIANA (default), CellPhoneDB, FastCCC, or CellChat
  (R). Skip when running scRNA-only L-R inference (use sc-cell-communication); no cell-type labels exist
  (use spatial-annotate).
trigger: cell communication, cell-cell communication, ligand receptor, ligand-receptor, LIANA, CellPhoneDB, FastCCC, CellChat
tags:
- spatial
- communication
- ligand-receptor
- liana
- cellphonedb
- cellchat
- fastccc
---

# spatial-communication

## When to use

The user has a preprocessed spatial AnnData with cell-type labels
(`obs[cell_type_key]`, default `leiden`) and wants ligand-receptor
cell-cell communication scored. Four backends:

- `liana` (default) — LIANA consensus across multiple L-R methods.
  Tunables `--liana-expr-prop`, `--liana-min-cells`, `--liana-n-perms`.
- `cellphonedb` — Permutation test with mean expression statistic.
  Tunables `--cellphonedb-iterations`, `--cellphonedb-threshold`.
- `fastccc` — Fast permutation-free percentile-based score.
  Tunables `--fastccc-min-percentile`.
- `cellchat_r` — CellChat (R) via `rpy2` interop. Tunables
  `--cellchat-min-cells`, `--cellchat-prob-type`.

Species: `--species human` (default) or `mouse`. For non-spatial
L-R use `sc-cell-communication`; for pathway scoring use
`spatial-enrichment`.

## Inputs & Outputs

**Inputs**

- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)
- Expects `obsm`: `spatial`

**Outputs**

- `tables/cellchat_centrality.csv`
- `tables/cellchat_count_matrix.csv`
- `tables/cellchat_pathways.csv`
- `tables/cellchat_results.csv`
- `tables/cellchat_weight_matrix.csv`
- `tables/communication_run_summary.csv`
- `tables/communication_spatial_points.csv`
- `tables/communication_summary.csv`
- `tables/communication_umap_points.csv`
- `tables/complex_composition_table.csv`
- `tables/complex_table.csv`
- `tables/gene_table.csv`
- `tables/interaction_table.csv`
- `tables/lr_interactions.csv`
- `tables/meta.tsv`
- `tables/protein_table.csv`
- `tables/signaling_roles.csv`
- `tables/source_target_summary.csv`
- `tables/top_interactions.csv`
- `figures/communication_pvalue_distribution.png`
- `figures/communication_roles_spatial.png`
- `figures/communication_score_vs_significance.png`
- `figures/lr_dotplot.png`
- `figures/lr_heatmap.png`
- `figures/lr_spatial.png`
- `figures/signaling_roles.png`
- `figures/source_target_summary.png`
- `fastccc_input.h5ad`
- `input.h5ad`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `uns`: `ccc_results`, `liana_results`, `cellphonedb_results`, `fastccc_results`, `cellchat_results`, `communication_summary`, `communication_signaling_roles`, `spatial_communication`

## Flow

1. Load AnnData, validate `obs[cell_type_key]` exists with ≥ 2 categories (`_lib/communication.py`).
2. Sync `obsm["spatial"]` ↔ `obsm["X_spatial"]` (`spatial_communication.py`); cast cell-type column to Categorical.
3. Dispatch to chosen backend (LIANA / CellPhoneDB / FastCCC / CellChat-R).
4. Write canonical L-R results to `uns["ccc_results"]` + per-method `uns[METHOD_RESULT_KEYS[method]]` (`_lib/communication.py`).
5. Compute pathway-level summary, signaling roles, source-target summary.
6. Save tables + `processed.h5ad` + report.

## Gotchas

- **`obs[cell_type_key]` is REQUIRED — no auto-fallback.** `_lib/communication.py` raises `ValueError` when the column is missing. Run `spatial-annotate` or `spatial-domains` first.
- **Default cell-type column is `leiden`, not `cell_type`.** `spatial_communication.py` defaults `--cell-type-key` to `"leiden"`. If your AnnData uses `cell_type`, pass `--cell-type-key cell_type` explicitly.
- **CellChat backend needs an R install with CellChat.** `--method cellchat_r` invokes R via `rpy2`. Install CellChat in your R environment first; missing R / rpy2 / CellChat surfaces as a runtime error inside the dispatch step (not at `parser.error`), so the failure happens after argument parsing succeeds.
- **FastCCC `--fastccc-min-percentile` must be in [0, 1].** `spatial_communication.py` rejects values outside that range with `parser.error`.
- **Output `uns` keys are unconditionally written, even with 0 interactions.** `_lib/communication.py` writes empty `uns["ccc_results"]` / `uns["communication_summary"]` if no L-R pairs pass thresholds — distinguish "no signal" from "method failed" by inspecting `tables/communication_run_summary.csv`.
- **Per-method copy uses `METHOD_RESULT_KEYS` mapping.** `_lib/communication.py` maps `liana → uns["liana_results"]`, `cellphonedb → uns["cellphonedb_results"]`, `fastccc → uns["fastccc_results"]`, `cellchat_r → uns["cellchat_results"]`. Downstream readers should prefer `uns["ccc_results"]` for portability.

## Key CLI

```bash
# Demo
python skills/spatial/spatial-communication/spatial_communication.py --demo --output /tmp/comm_demo

# LIANA consensus (default)
python skills/spatial/spatial-communication/spatial_communication.py \
  --input preprocessed.h5ad --output results/ \
  --method liana --species human --cell-type-key cell_type \
  --liana-expr-prop 0.1 --liana-min-cells 5 --liana-n-perms 1000

# CellPhoneDB permutation test
python skills/spatial/spatial-communication/spatial_communication.py \
  --input preprocessed.h5ad --output results/ \
  --method cellphonedb --cellphonedb-iterations 1000 --cellphonedb-threshold 0.1

# CellChat (R via rpy2)
python skills/spatial/spatial-communication/spatial_communication.py \
  --input preprocessed.h5ad --output results/ \
  --method cellchat_r --species mouse \
  --cellchat-min-cells 10 --cellchat-prob-type triMean
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins
- `references/output_contract.md` — `uns["ccc_results"]` schema + per-method copies
- Adjacent skills: `spatial-annotate` (upstream — provides `obs[cell_type_key]`), `spatial-domains` (upstream alternative — Leiden domains), `sc-cell-communication` (parallel — non-spatial L-R), `spatial-condition` (parallel — DE between conditions), `spatial-enrichment` (parallel — pathway scoring)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `cellphonedb`, `fastccc`, `liana`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
