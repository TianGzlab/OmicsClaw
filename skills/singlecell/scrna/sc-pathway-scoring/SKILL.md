---
name: sc-pathway-scoring
description: Load when computing per-cell pathway / gene-set scores on a normalised scRNA AnnData via
  AUCell (R or Python) or Scanpy score_genes. Skip when running condition-vs-control bulk-style enrichment
  on top of a DE table (use sc-enrichment); de-novo gene-program discovery (use sc-gene-programs).
trigger: pathway score, pathway scoring, gene set score, module score, pathway activity, signature score
tags:
- singlecell
- scrna
- pathway-scoring
- aucell
- scanpy-score-genes
- gene-sets
- decoupler
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

## Use in an analysis step

Use `load_skill` from the notebook SDK; write returned objects with
`write_output`. This runnable example is also in `examples/example_step.py`.
The CLI remains available for standalone reports and galleries.

```python
# Score PBMC lineage gene sets with the Python AUCell implementation.
# Reads pbmc3k_processed and uses its log-normalized raw snapshot.
# Calls sc-pathway-scoring: score_gene_sets, group_scores, score_distribution_figure.

from skills._sdk.notebook import load_demo, load_skill, write_output

pathways = load_skill('sc-pathway-scoring')
adata = load_demo('pbmc3k_processed').raw.to_adata()
gene_sets = {
    'B_cell': ['MS4A1', 'CD79A', 'CD79B', 'CD74', 'HLA-DRA'],
    'T_cell': ['CD3D', 'CD3E', 'CD3G', 'TRAC', 'IL7R'],
    'Myeloid': ['LYZ', 'S100A8', 'S100A9', 'FCN1', 'CTSS'],
}

scores = pathways.score_gene_sets(adata, gene_sets, method='aucell_py')
write_output(scores, 'tables/pathway_scores.csv')
write_output(pathways.group_scores(adata, scores, groupby='louvain'), 'tables/group_scores.csv')
write_output(pathways.score_distribution_figure(scores), 'figures/score_distribution.png')

assert scores.index.equals(adata.obs_names)
assert set(scores.columns) == set(gene_sets)
assert scores.max().max() > 0
assert scores.min().min() >= 0
```

## Inputs & Outputs

Input is an AnnData and gene sets keyed by name. The CLI reads H5AD plus a
GMT file or an Enrichr library. Python scoring returns a cell-by-set
DataFrame; `attach_scores` returns a copy with `obs["enrich__..."]` columns.

The CLI writes `processed.h5ad`, `report.md`, `result.json`, and
`tables/enrichment_scores.csv`, `gene_set_overlap.csv`, `top_pathways.csv`.
Grouped runs also write `group_mean_scores.csv` and
`group_high_fraction.csv`. Plot source tables live under `figure_data/`,
not `tables/`. R exchange matrices and AUCell CSVs are temporary.

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

- `run_info(scores)["skipped_gene_sets"]` lists sets with no matching features. Inspect `tables/gene_set_overlap.csv` before interpreting scores; all-unmatched Python input raises.
- `score_gene_sets(..., method="score_genes_py")` requires normalized X. AUCell ranks expression and can also use counts.
- `load_gene_sets` downloads named libraries through gseapy. Local GMT/JSON avoids network access. This skill's mouse `kegg` alias is `KEGG_2021_Mouse`, intentionally separate from sc-enrichment's aliases.
- `aucell_r` needs AUCell and GSEABase. Its temporary result must contain a `Cell` column; otherwise the API raises instead of misaligning rows.
- API scoring uses seed 42 by default. The CLI preserves its historical `score_genes_py` seed 0; its AUCell seed defaults to 42. Set `random_state=0` for API/CLI score_genes comparisons.
- `processed.h5ad` adds an `enrich__` obs column per gene set. `attach_scores` copies its input; `score_gene_sets` leaves it unchanged.
- CLI `--demo` slices the first 60 feature names into four arbitrary sets. They exercise the pipeline, not biological pathways. The step below uses named PBMC lineage genes.

## Key CLI

```bash
# Demo (built-in gene sets)
python skills/singlecell/scrna/sc-pathway-scoring/sc_pathway_scoring.py --demo --output /tmp/sc_pw_demo

# AUCell-R with MSigDB Hallmark, grouped by cell type
python skills/singlecell/scrna/sc-pathway-scoring/sc_pathway_scoring.py \
  --input clustered.h5ad --output results/ \
  --gene-set-db hallmark --groupby cell_type

# AUCell-Python (no R needed) with custom GMT
python skills/singlecell/scrna/sc-pathway-scoring/sc_pathway_scoring.py \
  --input clustered.h5ad --output results/ \
  --method aucell_py --gene-sets pathways.gmt --groupby leiden

# Scanpy score_genes for fast prototyping
python skills/singlecell/scrna/sc-pathway-scoring/sc_pathway_scoring.py \
  --input clustered.h5ad --output results/ \
  --method score_genes_py --gene-sets pathways.gmt
```

## See also

- `references/parameters.md` — every CLI flag, library aliases
- `references/methodology.md` — AUCell vs score_genes; gene-symbol expectations
- `references/output_contract.md` — `enrichment_scores.csv` schema; per-method differences
- Adjacent skills: `sc-clustering` / `sc-cell-annotation` (upstream — produce `--groupby` column for group-aware aggregates), `sc-enrichment` (parallel — bulk-style GSEA/ORA on DE tables, NOT per-cell scoring), `sc-gene-programs` (parallel — de-novo factorisation, NOT supervised scoring against curated sets), `sc-grn` (parallel — TF-target regulons; AUCell is shared underlying tech)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `gseapy`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `score_gene_sets(adata, gene_sets, *, method: str='aucell_r', auc_max_rank: int | None=None, auc_threshold: float=0.05, ctrl_size: int=50, n_bins: int=25, random_state: int=42) -> pd.DataFrame`

Return cell-by-gene-set scores without changing adata.

aucell_py ranks X, breaking ties with random_state; auc_threshold is the
fraction of ranked genes used. score_genes_py requires normalized X and
uses Scanpy control genes. aucell_r requires AUCell/GSEABase and uses
normalized X or an aligned raw matrix. R exchange files are temporary.
Gene sets with no matched features are skipped; all-unmatched input fails.
API seeds default to 42. The historical score_genes CLI uses seed 0.

### `load_gene_sets(source, *, species: str='human') -> dict[str, list[str]]`

Read a GMT or JSON file, or download an Enrichr library.

Aliases belong to this skill: mouse KEGG resolves to KEGG_2021_Mouse.
Named libraries require gseapy and network access; local files do not.

### `attach_scores(adata, scores: pd.DataFrame)`

Return a copy with enrich__ columns and the scoring run record in uns.

### `gene_set_overlap(adata, gene_sets) -> pd.DataFrame`

Return matched feature counts and identifiers for every requested gene set.

### `group_scores(adata, scores: pd.DataFrame, *, groupby: str) -> pd.DataFrame`

Return mean scores per obs group, retaining every scored gene set.

### `top_pathways(scores: pd.DataFrame, *, n: int=20) -> pd.DataFrame`

Rank gene sets by mean absolute cell score, breaking ties by name.

### `score_summary(adata, scores_df: pd.DataFrame, *, groupby: str | None, top_pathways: int) -> dict[str, object]`

Return top pathways, grouped means, high fractions and long-form scores.

### `score_distribution_figure(scores: pd.DataFrame)`

Return a boxplot of per-cell scores without writing files.

### `run_info(result) -> dict`

Return the scoring method, seed, feature source and skipped sets.

<!-- api:end -->
