---
name: spatial-communication
description: Load when computing ligand-receptor cell-cell communication on a preprocessed spatial AnnData with `obs[cell_type_key]` (default `leiden`) via LIANA (default), CellPhoneDB, FastCCC, or CellChat (R). Skip when running scRNA-only L-R inference (use `sc-cell-communication`) or when no cell-type labels exist (run `spatial-annotate` or `spatial-domains` first).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- spatial
- communication
- ligand-receptor
- liana
- cellphonedb
- cellchat
- fastccc
requires:
- anndata
- scanpy
- numpy
- pandas
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

| Input | Format | Required |
|---|---|---|
| Preprocessed spatial AnnData | `.h5ad` with `obsm["spatial"]`, `obs[cell_type_key]` (default `leiden`) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | `uns["ccc_results"]` (canonical L-R DataFrame); per-method copy at `uns["liana_results"]` / `uns["cellphonedb_results"]` / `uns["fastccc_results"]` / `uns["cellchat_results"]`; `uns["communication_summary"]` (pathway-level); `uns["communication_signaling_roles"]` (sender/receiver scores); `uns["spatial_communication"]` (run metadata) |
| L-R interactions | `tables/lr_interactions.csv` | full L-R list |
| Top interactions | `tables/top_interactions.csv` | top-N filtered |
| Pathway summary | `tables/communication_summary.csv` | aggregate per pathway |
| Signaling roles | `tables/signaling_roles.csv` | sender/receiver per cell type |
| Source-target | `tables/source_target_summary.csv` | per source-target pair counts |
| Run summary | `tables/communication_run_summary.csv` | params used |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData, validate `obs[cell_type_key]` exists with ≥ 2 categories (`_lib/communication.py:764-765`).
2. Sync `obsm["spatial"]` ↔ `obsm["X_spatial"]` (`spatial_communication.py:79-81`); cast cell-type column to Categorical.
3. Dispatch to chosen backend (LIANA / CellPhoneDB / FastCCC / CellChat-R).
4. Write canonical L-R results to `uns["ccc_results"]` + per-method `uns[METHOD_RESULT_KEYS[method]]` (`_lib/communication.py:735-739`).
5. Compute pathway-level summary, signaling roles, source-target summary.
6. Save tables + `processed.h5ad` + report.

## Gotchas

- **`obs[cell_type_key]` is REQUIRED — no auto-fallback.** `_lib/communication.py:764-765` raises `ValueError` when the column is missing. Run `spatial-annotate` or `spatial-domains` first.
- **Default cell-type column is `leiden`, not `cell_type`.** `spatial_communication.py:1065` defaults `--cell-type-key` to `"leiden"`. If your AnnData uses `cell_type`, pass `--cell-type-key cell_type` explicitly.
- **CellChat backend needs an R install with CellChat.** `--method cellchat_r` invokes R via `rpy2`. Install CellChat in your R environment first; missing R / rpy2 / CellChat surfaces as a runtime error inside the dispatch step (not at `parser.error`), so the failure happens after argument parsing succeeds.
- **FastCCC `--fastccc-min-percentile` must be in [0, 1].** `spatial_communication.py:985` rejects values outside that range with `parser.error`.
- **Output `uns` keys are unconditionally written, even with 0 interactions.** `_lib/communication.py:735-739` writes empty `uns["ccc_results"]` / `uns["communication_summary"]` if no L-R pairs pass thresholds — distinguish "no signal" from "method failed" by inspecting `tables/communication_run_summary.csv`.
- **Per-method copy uses `METHOD_RESULT_KEYS` mapping.** `_lib/communication.py:68-73` maps `liana → uns["liana_results"]`, `cellphonedb → uns["cellphonedb_results"]`, `fastccc → uns["fastccc_results"]`, `cellchat_r → uns["cellchat_results"]`. Downstream readers should prefer `uns["ccc_results"]` for portability.

## Key CLI

```bash
# Demo
python omicsclaw.py run spatial-communication --demo --output /tmp/comm_demo

# LIANA consensus (default)
python omicsclaw.py run spatial-communication \
  --input preprocessed.h5ad --output results/ \
  --method liana --species human --cell-type-key cell_type \
  --liana-expr-prop 0.1 --liana-min-cells 5 --liana-n-perms 1000

# CellPhoneDB permutation test
python omicsclaw.py run spatial-communication \
  --input preprocessed.h5ad --output results/ \
  --method cellphonedb --cellphonedb-iterations 1000 --cellphonedb-threshold 0.1

# CellChat (R via rpy2)
python omicsclaw.py run spatial-communication \
  --input preprocessed.h5ad --output results/ \
  --method cellchat_r --species mouse \
  --cellchat-min-cells 10 --cellchat-prob-type triMean
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins
- `references/output_contract.md` — `uns["ccc_results"]` schema + per-method copies
- Adjacent skills: `spatial-annotate` (upstream — provides `obs[cell_type_key]`), `spatial-domains` (upstream alternative — Leiden domains), `sc-cell-communication` (parallel — non-spatial L-R), `spatial-condition` (parallel — DE between conditions), `spatial-enrichment` (parallel — pathway scoring)
