---
name: sc-drug-response
description: Load when scoring drug sensitivity per cluster on an annotated scRNA AnnData via simple-correlation against drug-target signatures or via CaDRReS-Sc pretrained models (GDSC / PRISM). Skip when the AnnData has no cluster labels yet (run sc-clustering first) or for predicting genetic-perturbation effects (use sc-in-silico-perturbation).
version: 0.2.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- drug-response
- pharmacogenomics
- cadrres
- gdsc
- prism
requires:
- anndata
- scanpy
- numpy
- pandas
---

# sc-drug-response

## When to use

The user has a clustered / labelled scRNA AnnData with HGNC-symbol gene
names and wants per-cluster drug sensitivity rankings. Two methods:

- `simple_correlation` (default) — built-in lightweight scorer:
  correlates per-cluster mean expression with drug-target signatures
  from `_BUILTIN_DRUG_TARGETS`. No external models, no CaDRReS install.
- `cadrres` — runs CaDRReS-Sc against pretrained GDSC or PRISM models.
  Requires the CaDRReS-Sc script directory plus model files locally
  (cache at `~/.cache/omicsclaw/cadrres/<drug-db>/`).

For *genetic* perturbation predictions (KO / KD / overexpression on
unperturbed data) use `sc-in-silico-perturbation`. For real Perturb-seq
classification use `sc-perturb`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Clustered AnnData (HGNC symbols in `var_names`) | `.h5ad` with cluster column in `obs` | yes (unless `--demo`) |
| CaDRReS model dir | path (`--model-dir`) | required for `cadrres` (real runs only) |

| Output | Path | Notes |
|---|---|---|
| AnnData (preserved) | `processed.h5ad` | unchanged unless cluster_key was auto-resolved |
| Drug rankings | `tables/drug_rankings.csv` | per-cluster × drug score table; column `Score` |
| Figures | `figures/top_drugs_bar.png`, `figures/drug_cluster_heatmap.png`, `figures/drug_sensitivity_umap.png` | best-effort: UMAP overlay skipped when `obsm["X_umap"]` is missing (`sc_drug_response.py:447-449`); bar / heatmap calls are wrapped in `try / except` (`:814-826`) and only log on failure |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData; resolve `--cluster-key` (auto-pick from `leiden` / `louvain` / `cell_type` / first categorical if unset).
2. Preflight: `cluster_key` exists + has ≥ 2 groups (warn-only on < 2); gene-name overlap with drug targets.
3. For `cadrres`: validate `--model-dir` has the GDSC / PRISM files + locate the CaDRReS-Sc script directory; run via `Drug_Response` wrapper.
4. For `simple_correlation`: compute per-cluster expression means, correlate against `_BUILTIN_DRUG_TARGETS`, rank drugs per cluster.
5. Detect degenerate output (empty rankings / all-NaN scores) → print multi-action fix message; do NOT raise.
6. Render bar / heatmap / UMAP figures, write `tables/drug_rankings.csv`, save `report.md`, `result.json`.

## Gotchas

- **Gene-name nomenclature is enforced.** `sc_drug_response.py:193` raises `ValueError` when 0% of `_BUILTIN_DRUG_TARGETS` overlap with `var_names`. The error inspects sample gene names — if they look like `ENSG*` / `ENSMUSG*`, the message points to `bulkrna-geneid-mapping`; otherwise to `sc-standardize-input`. Below 20 % overlap is a warning (not a fail) — results may still be unreliable.
- **`cadrres` needs both model files AND a CaDRReS-Sc script dir.** `sc_drug_response.py:146` raises `FileNotFoundError` listing missing model files in `--model-dir`; `sc_drug_response.py:385` raises a separate `FileNotFoundError("CaDRReS-Sc script directory not found.")` when the script dir isn't at `<model-dir>/../CaDRReS-Sc` or `~/CaDRReS-Sc`. Both error messages embed the full `CADRRES_DOWNLOAD_INSTRUCTIONS`.
- **`cadrres` demo bypasses real model.** `sc_drug_response.py:761-764` auto-generates synthetic CaDRReS scores when `--method cadrres --demo` — reported drugs are random; only use for plumbing checks.
- **Auto-cluster-key resolution falls through to "first categorical".** `sc_drug_response.py:729` searches `("leiden", "louvain", "cluster", "cell_type", "celltype")` in order; `:733-737` falls through to the first categorical-dtype obs column (with a warning); `:739-742` raises `ValueError("No cluster labels found in adata.obs. Run sc-preprocessing first, or specify --cluster-key.")` only when nothing is categorical. Using a stray categorical column (e.g., `sample_id` cast as Category) silently produces meaningless rankings — always pass `--cluster-key` explicitly on real data.
- **Degenerate output is a soft fail.** When `simple_correlation` finds no overlapping drug targets or `cadrres` returns empty, lines 770+ print a multi-option fix message but the script returns 0. Always check `result.json["n_drugs_scored"]` (line 846) — `0` means the run was uninformative.
- **`--input` mandatory unless `--demo`.** `sc_drug_response.py:722` raises `ValueError("--input required when not using --demo")`.
- **Unknown `--method` rejected post-argparse.** `sc_drug_response.py:767` raises `ValueError(f"Unknown method: {method}")`. argparse `choices` should catch this first via METHOD_REGISTRY (`:697`); the manual raise is a safety net.

## Key CLI

```bash
# Demo (synthetic scores, simple_correlation)
python omicsclaw.py run sc-drug-response --demo --output /tmp/sc_drug_demo

# Default simple correlation against built-in drug targets
python omicsclaw.py run sc-drug-response \
  --input clustered.h5ad --output results/ --cluster-key leiden

# CaDRReS with GDSC model
python omicsclaw.py run sc-drug-response \
  --input clustered.h5ad --output results/ \
  --method cadrres --drug-db gdsc --model-dir ~/.cache/omicsclaw/cadrres/gdsc/

# CaDRReS with PRISM, top 50 drugs
python omicsclaw.py run sc-drug-response \
  --input clustered.h5ad --output results/ \
  --method cadrres --drug-db prism --n-drugs 50
```

## See also

- `references/parameters.md` — every CLI flag, model-dir conventions
- `references/methodology.md` — `simple_correlation` math vs CaDRReS; gene-symbol expectations
- `references/output_contract.md` — `tables/drug_rankings.csv` column schema
- Adjacent skills: `sc-clustering` (upstream — produces the cluster column), `sc-cell-annotation` (parallel — biological labels often work better than `leiden` for drug interpretability), `sc-in-silico-perturbation` (parallel — predicts genetic perturbation effects, NOT drug sensitivity), `bulkrna-geneid-mapping` / `sc-standardize-input` (upstream remediation — convert Ensembl IDs to HGNC symbols if the preflight fails)
