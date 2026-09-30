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

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/IC50_prediction.csv`
- `tables/PRISM_prediction.csv`
- `tables/cell_metadata.csv`
- `tables/drug_rankings.csv`
- `tables/masked_drugs.csv`
- `figures/drug_cluster_heatmap.png`
- `figures/drug_sensitivity_umap.png`
- `figures/top_drugs_bar.png`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `drug_score_<drug>`

## Flow

1. Load AnnData; resolve `--cluster-key` (auto-pick from `leiden` / `louvain` / `cell_type` / first categorical if unset).
2. Preflight: `cluster_key` exists + has ≥ 2 groups (warn-only on < 2); gene-name overlap with drug targets.
3. For `cadrres`: validate `--model-dir` has the GDSC / PRISM files + locate the CaDRReS-Sc script directory; run via `Drug_Response` wrapper.
4. For `simple_correlation`: compute per-cluster expression means, correlate against `_BUILTIN_DRUG_TARGETS`, rank drugs per cluster.
5. Detect degenerate output (empty rankings / all-NaN scores) → print multi-action fix message; do NOT raise.
6. Render bar / heatmap / UMAP figures, write `tables/drug_rankings.csv`, save `report.md`, `result.json`.

## Gotchas

- **Gene-name nomenclature is enforced.** `sc_drug_response.py` raises `ValueError` when 0% of `_BUILTIN_DRUG_TARGETS` overlap with `var_names`. The error inspects sample gene names — if they look like `ENSG*` / `ENSMUSG*`, the message points to `bulkrna-geneid-mapping`; otherwise to `sc-standardize-input`. Below 20 % overlap is a warning (not a fail) — results may still be unreliable.
- **`cadrres` needs both model files AND a CaDRReS-Sc script dir.** `sc_drug_response.py` raises `FileNotFoundError` listing missing model files in `--model-dir`; raises a separate `FileNotFoundError("CaDRReS-Sc script directory not found.")` when the script dir isn't at `<model-dir>/../CaDRReS-Sc` or `~/CaDRReS-Sc`. Both error messages embed the full `CADRRES_DOWNLOAD_INSTRUCTIONS`.
- **`cadrres` demo bypasses real model.** `sc_drug_response.py` auto-generates synthetic CaDRReS scores when `--method cadrres --demo` — reported drugs are random; only use for plumbing checks.
- **Auto-cluster-key resolution falls through to "first categorical".** `sc_drug_response.py` searches `("leiden", "louvain", "cluster", "cell_type", "celltype")` in order; falls through to the first categorical-dtype obs column (with a warning); raises `ValueError("No cluster labels found in adata.obs. Run sc-preprocessing first, or specify --cluster-key.")` only when nothing is categorical. Using a stray categorical column (e.g., `sample_id` cast as Category) silently produces meaningless rankings — always pass `--cluster-key` explicitly on real data.
- **Degenerate output is a soft fail.** When `simple_correlation` finds no overlapping drug targets or `cadrres` returns empty, `main` prints a multi-option fix message but the script returns 0. Always check `result.json["n_drugs_scored"]` — `0` means the run was uninformative.
- **`--input` mandatory unless `--demo`.** `sc_drug_response.py` raises `ValueError("--input required when not using --demo")`.
- **Unknown `--method` rejected post-argparse.** `sc_drug_response.py` raises `ValueError(f"Unknown method: {method}")`. argparse `choices` should catch this first via METHOD_REGISTRY; the manual raise is a safety net.

## Key CLI

```bash
# Demo (synthetic scores, simple_correlation)
python skills/singlecell/scrna/sc-drug-response/sc_drug_response.py --demo --output /tmp/sc_drug_demo

# Default simple correlation against built-in drug targets
python skills/singlecell/scrna/sc-drug-response/sc_drug_response.py \
  --input clustered.h5ad --output results/ --cluster-key leiden

# CaDRReS with GDSC model
python skills/singlecell/scrna/sc-drug-response/sc_drug_response.py \
  --input clustered.h5ad --output results/ \
  --method cadrres --drug-db gdsc --model-dir ~/.cache/omicsclaw/cadrres/gdsc/

# CaDRReS with PRISM, top 50 drugs
python skills/singlecell/scrna/sc-drug-response/sc_drug_response.py \
  --input clustered.h5ad --output results/ \
  --method cadrres --drug-db prism --n-drugs 50
```

## See also

- `references/parameters.md` — every CLI flag, model-dir conventions
- `references/methodology.md` — `simple_correlation` math vs CaDRReS; gene-symbol expectations
- `references/output_contract.md` — `tables/drug_rankings.csv` column schema
- Adjacent skills: `sc-clustering` (upstream — produces the cluster column), `sc-cell-annotation` (parallel — biological labels often work better than `leiden` for drug interpretability), `sc-in-silico-perturbation` (parallel — predicts genetic perturbation effects, NOT drug sensitivity), `bulkrna-geneid-mapping` / `sc-standardize-input` (upstream remediation — convert Ensembl IDs to HGNC symbols if the preflight fails)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `omicverse`, `pandas`, `scanpy`, `scipy`, `seaborn`
