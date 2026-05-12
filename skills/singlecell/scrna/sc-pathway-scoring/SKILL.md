---
name: sc-pathway-scoring
description: Load when computing per-cell pathway / gene-set scores on a normalised scRNA AnnData via AUCell (R or Python) or Scanpy score_genes. Skip when running condition-vs-control bulk-style enrichment on top of a DE table (use sc-enrichment) or for de-novo gene-program discovery (use sc-gene-programs).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- pathway-scoring
- aucell
- scanpy-score-genes
- gene-sets
- decoupler
requires:
- anndata
- scanpy
- numpy
- pandas
---

# sc-pathway-scoring

## When to use

The user has a normalised scRNA AnnData and a gene-set library (GMT
file or one of the built-in DB aliases: `hallmark`, `kegg`, `reactome`,
`go_bp`, ...) and wants per-cell scores quantifying how active each
gene set is. Three methods:

- `aucell_r` (default) — R-backed AUCell via `decoupler-py`-style
  bridge. Best statistical foundation; requires R env.
- `aucell_py` — Python AUCell (`--aucell-py-auc-threshold`). Pure
  Python.
- `score_genes_py` — Scanpy `tl.score_genes` per gene set. Lightest
  and fastest.

Output: `tables/enrichment_scores.csv` (cells × gene_sets), plus
group-mean / group-high-fraction tables when `--groupby` is provided.

For *bulk-style* condition-vs-control GSEA / ORA on a DE table use
`sc-enrichment`. For de-novo gene-program discovery use
`sc-gene-programs`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Normalised AnnData | `.h5ad` | yes (unless `--demo`) |
| Gene sets | `.gmt` (`--gene-sets`) **OR** library alias (`--gene-set-db hallmark`/`kegg`/`reactome`/`go_bp`) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | adds per-cell pathway scores in `obs` (one column per gene set) |
| Per-cell scores | `tables/enrichment_scores.csv` | cells × gene_sets |
| Gene-set overlap | `tables/gene_set_overlap.csv` | how many input genes survived the feature mapping |
| Top pathways | `tables/top_pathways.csv` | top-`--top-pathways` ranked gene sets |
| Group means | `tables/group_mean_scores.csv` | when `--groupby` is provided |
| Group high-fraction | `tables/group_high_fraction.csv` | when `--groupby` is provided |
| Figures | `top_gene_sets.png`, `group_mean_heatmap.png`, `group_mean_dotplot.png`, `top_pathway_distributions.png`, `embedding_top_pathways.png` | rendered via `skills/singlecell/_lib/viz/enrichment.py`; group-aware ones require `--groupby` |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or build a demo.
2. Load gene sets: parse `--gene-sets` GMT, OR fetch via `--gene-set-db <alias>` and write a resolved GMT.
3. Validate: at least one gene-set member overlaps the input features (`feature_label_source` chosen from `var_names` / `var["gene_symbol"]` / etc.).
4. Run preflight; resolve `--groupby` (auto-pick from `leiden` / `louvain` / `cell_type` if unset).
5. Dispatch to method:
   - `aucell_r`: shell out to bundled R script via `RScriptRunner`.
   - `aucell_py`: AUCell-Python with `--aucell-py-auc-threshold`.
   - `score_genes_py`: Scanpy `tl.score_genes` per gene set.
6. Compute group-aware aggregates if `--groupby` is set.
7. Save tables, figures, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **Zero-overlap between gene sets and input features is a hard fail.** `sc_pathway_scoring.py:171` raises `ValueError(f"No valid gene sets were parsed from {gene_sets_path}")` for malformed GMT files; `:435` raises `ValueError("No gene sets had any overlap with the input features, so no enrichment scores could be computed.")` and `:885-887` raises `ValueError("None of the supplied gene-set members matched the input features. ...")` when the merged overlap table sums to 0. Run `sc-standardize-input` upstream if gene names need canonicalisation, or pass `--gene-sets` with matching ID space.
- **`score_genes_py` requires `.X` to be normalised expression.** `sc_pathway_scoring.py:413` raises `ValueError("`score_genes_py` requires normalized expression in `adata.X`. Run `sc-preprocessing` first.")`. The other two methods (`aucell_r`, `aucell_py`) use rank-based scoring and are tolerant of raw counts.
- **`--gene-set-db` library lookup can fail in three ways (gseapy / Python side).** `sc_pathway_scoring.py:354` raises `ImportError("--gene-set-db requires gseapy. ...")` when gseapy isn't installed; `:363` raises `RuntimeError("Failed to download or resolve gene-set library ...")` on a network / unknown-library failure; `:368` raises `ValueError("Gene-set library ... returned no gene sets ...")` when gseapy returns an empty dict. All three are pre-AUCell — fix gseapy or supply a local `--gene-sets` GMT.
- **`aucell_r` R environment is validated separately (R side).** `sc_pathway_scoring.py:381` calls `validate_r_environment(required_r_packages=["AUCell", "GSEABase"])` which raises if the R bridge is missing AUCell / GSEABase. After the R subprocess returns, `:400` raises `ValueError("AUCell output is missing the required 'Cell' column")` when the R-Python data round-trip drops the cell index.
- **One of `--gene-sets` or `--gene-set-db` is required.** `sc_pathway_scoring.py:858` raises `ValueError("--input required when not using --demo")`; `:860` raises `ValueError("--gene-sets or --gene-set-db is required unless --demo is used")` when both are unset on a real run. Library aliases are: `hallmark`, `kegg`, `reactome`, `go_bp` — others are passed through to the EnrichR library API.
- **`--gene-sets` file existence is checked, format is not pre-validated.** `sc_pathway_scoring.py:866` raises `FileNotFoundError(f"Gene set file not found: {gene_sets_path}")` for a missing path. Empty / malformed GMT survives this check and triggers `:171` later.
- **`obs` is mutated: one column per gene set.** When the run completes, `processed.h5ad` has new `obs` columns (one per gene set name). For large libraries (e.g., `MSigDB_Hallmark_2020` has 50 sets, KEGG_2021 has 320) this can dramatically bloat `obs`. Filter or namespace the gene sets if downstream tools struggle.

## Key CLI

```bash
# Demo (built-in gene sets)
python omicsclaw.py run sc-pathway-scoring --demo --output /tmp/sc_pw_demo

# AUCell-R with MSigDB Hallmark, grouped by cell type
python omicsclaw.py run sc-pathway-scoring \
  --input clustered.h5ad --output results/ \
  --gene-set-db hallmark --groupby cell_type

# AUCell-Python (no R needed) with custom GMT
python omicsclaw.py run sc-pathway-scoring \
  --input clustered.h5ad --output results/ \
  --method aucell_py --gene-sets pathways.gmt --groupby leiden

# Scanpy score_genes for fast prototyping
python omicsclaw.py run sc-pathway-scoring \
  --input clustered.h5ad --output results/ \
  --method score_genes_py --gene-sets pathways.gmt
```

## See also

- `references/parameters.md` — every CLI flag, library aliases
- `references/methodology.md` — AUCell vs score_genes; gene-symbol expectations
- `references/output_contract.md` — `enrichment_scores.csv` schema; per-method differences
- Adjacent skills: `sc-clustering` / `sc-cell-annotation` (upstream — produce `--groupby` column for group-aware aggregates), `sc-enrichment` (parallel — bulk-style GSEA/ORA on DE tables, NOT per-cell scoring), `sc-gene-programs` (parallel — de-novo factorisation, NOT supervised scoring against curated sets), `sc-grn` (parallel — TF-target regulons; AUCell is shared underlying tech)
