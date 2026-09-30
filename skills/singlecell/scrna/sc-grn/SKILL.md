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

## When to use

The user has a normalised scRNA AnnData (cluster labels in
`obs[--cluster-key]`, default `leiden`) and wants gene regulatory
network inference: TFs → target genes plus per-cell regulon activity
scores. Two paths:

- **Full SCENIC pipeline** (when `--tf-list` + `--db` + `--motif` are
  all provided): GRNBoost2 co-expression → cisTarget motif enrichment
  + pruning → AUCell scoring per cell. Produces motif-validated
  regulons; AUCell activity is exposed as **per-TF `obs["regulon_<TF>"]` columns** (one float column per regulon) plus `tables/grn_auc_matrix.csv`.
- **Correlation fallback** (when external resources are missing AND
  `--allow-simplified-grn` is set, or in `--demo`): adjacency-only
  output, no motif validation, no AUCell. Useful for sanity checks
  but NOT a substitute for the full pipeline.

For ligand-receptor / cell-cell communication use
`sc-cell-communication`. For in-silico KO predictions use
`sc-in-silico-perturbation` (which builds a simpler GRN internally).

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`, `.txt`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/auc_matrix.csv`
- `tables/cell_metadata.csv`
- `tables/gene_expression.csv`
- `tables/regulon_summary.csv`
- `tables/top_adjacencies.csv`
- `figures/r_regulon_cor.png`
- `figures/r_regulon_violin.png`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `regulon_<TF>`

## Flow

1. Load AnnData (`--input`) or build a synthetic demo (GRNBoost2-only).
2. Preflight: when running the full pipeline, verify `--tf-list` / `--db` / `--motif` exist; demo / `--allow-simplified-grn` skip the resource check.
3. Try GRNBoost2 (arboreto) for co-expression adjacencies; if `arboreto` is not installed OR returns empty, **silently fall back to correlation-based adjacencies** and record `result.json["used_fallback"]=True` + `fallback_reason`.
4. With full resources: run cisTarget motif enrichment + pruning → AUCell scoring per cell.
5. Detect degenerate output (zero regulons / TFs) → write troubleshooting block; do NOT raise.
6. Save tables, figures, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **Silent fallback to correlation GRN when `arboreto` is missing or fails.** `sc_grn.py` catches `ImportError` for arboreto, sets `used_fallback=True`, `fallback_reason="arboreto package not installed"`; catches general exceptions / empty results with `fallback_reason` set accordingly. The fallback adjacency-only mode skips motif validation AND AUCell — `tables/grn_auc_matrix.csv` won't be written. The persisted `result.json["used_fallback"]` is set in the top-level summary at `sc_grn.py`.
- **`--input` is `parser.error` (exit code 2), not `ValueError`.** `sc_grn.py` calls `parser.error("--input required when not using --demo")`. Once `--input` is given, `main` raises `FileNotFoundError(f"Input file not found: {input_path}\nProvide a valid preprocessed .h5ad file, or use --demo for a quick test.")` for a missing path.
- **Full SCENIC needs ALL THREE external resources.** `--tf-list` + `--db` + `--motif` must be provided together; the preflight at `sc_grn.py` enforces this unless `--demo` or `--allow-simplified-grn` bypasses. Resources must be downloaded separately (cisTarget DBs from `https://resources.aertslab.org/cistarget/`).
- **Two distinct degenerate-output modes.** *Total failure* (`result is None`): `sc_grn.py` writes the degenerate-diag block and **calls `sys.exit(1)`** (caller wrappers expecting a 0 exit will see a hard fail). *Partial degeneracy* (`_check_degenerate_output` returns a non-None diagnostic with regulons-but-uninformative): the script proceeds to a soft-warn finish and exits 0. Always check `result.json["n_regulons"]` AND the process exit code before chaining downstream.
- **`processed.h5ad` per-regulon `obs["regulon_<TF>"]` columns only exist when AUCell ran.** In the correlation-fallback or no-motif path, `processed.h5ad` is essentially the input AnnData with contract metadata only — no `regulon_*` `obs` columns and no `tables/grn_auc_matrix.csv`. Downstream skills consuming regulon activity must check for the columns' presence first.
- **`--cluster-key` defaults to `leiden`.** `sc_grn.py` defaults to `leiden`. If the AnnData has labels under a different key (e.g., `cell_type`), pass `--cluster-key cell_type` so the per-cluster regulon-activity heatmap is meaningful.

## Key CLI

```bash
# Demo (correlation-based, no external resources)
python skills/singlecell/scrna/sc-grn/sc_grn.py --demo --output /tmp/sc_grn_demo

# Full SCENIC pipeline with all 3 external resources
python skills/singlecell/scrna/sc-grn/sc_grn.py \
  --input clustered.h5ad --output results/ \
  --tf-list /refs/cistarget/hsapiens_TFs.txt \
  --db '/refs/cistarget/hg38_*.feather' \
  --motif /refs/cistarget/motifs-v9-nr.hgnc-m0.001-o0.0.tbl \
  --n-jobs 8

# Correlation-only (when SCENIC resources unavailable, explicit opt-in)
python skills/singlecell/scrna/sc-grn/sc_grn.py \
  --input clustered.h5ad --output results/ \
  --allow-simplified-grn

# Custom cluster key + tighter target budget
python skills/singlecell/scrna/sc-grn/sc_grn.py \
  --input annotated.h5ad --output results/ \
  --tf-list tf.txt --db '/refs/*.feather' --motif motifs.tbl \
  --cluster-key cell_type --n-top-targets 25
```

## See also

- `references/parameters.md` — every CLI flag, resource-format conventions
- `references/methodology.md` — GRNBoost2 → cisTarget → AUCell flow; correlation-fallback semantics
- `references/output_contract.md` — per-regulon `obs["regulon_<TF>"]` columns; adjacency / regulon CSV columns
- Adjacent skills: `sc-clustering` (upstream — produces `obs["leiden"]`), `sc-batch-integration` (upstream — integrated embedding for cleaner co-expression), `sc-cell-communication` (parallel — L-R signalling, NOT TF→target), `sc-in-silico-perturbation` (parallel — predicts KO effects with a smaller internal GRN), `sc-pathway-scoring` (parallel — per-cell pathway scores; complementary to AUCell regulon scores)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `arboreto`, `dask`, `matplotlib`, `networkx`, `numpy`, `pandas`, `pyscenic`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`
