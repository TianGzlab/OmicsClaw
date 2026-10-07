---
name: sc-enrichment
description: Load when running bulk-style pathway enrichment (ORA / GSEA / GSEA-R / GSVA-R) on a per-group
  ranked DE / marker list against a gene-set library. Skip when computing per-cell pathway scores in-place
  (use sc-pathway-scoring); de-novo gene-program discovery (use sc-gene-programs).
trigger: sc enrichment, single-cell enrichment, GO enrichment, KEGG enrichment, GSEA, ORA, pathway enrichment
tags:
- singlecell
- scrna
- enrichment
- gsea
- ora
- gsva
- decoupler
- pathway-enrichment
---

# sc-enrichment

## When to use

Test named gene sets against per-group marker/DE rankings with ORA or GSEA.
GSVA scores mean expression per group in R. For scores per cell use
`sc-pathway-scoring`; for programmes discovered without gene sets use
`sc-gene-programs`.

## Steps

Start a step with `python skills/_sdk/notebook/run.py new enrichment`.
Load `enrichment = load_skill("sc-enrichment")`, then call `rank_groups`,
`load_gene_sets` (GMT, JSON or Enrichr library), and `ora` or `gsea`.
Pass the complete tested gene universe as `background` for ORA; its API
default is all genes in the supplied ranking. Write returned tables and
Figures with `write_output`. See `examples/example_step.py`.

The default engine is Python. Explicit `engine="auto"` prefers R when its
packages are available; `engine="r"` requires clusterProfiler. The legacy
`gsea_r` method uses GO_BP/KEGG/Reactome annotation databases, not custom GMT.
`gsva` accepts a gene-set mapping, or None for the GO_BP/KEGG R database route.

## Inputs & Outputs

Rankings need gene/names and a score or effect, with an optional group column.
`rank_groups` reads log-normalised `X`, never `raw`. For the processed PBMC
demo, use `.raw.to_adata()` in new steps; the CLI retains its old scaled-X
demo ranking for compatibility. The CLI accepts H5AD or an upstream output
directory containing `processed.h5ad` and marker/DE tables.

ORA/GSEA CLI writes `processed.h5ad`, `report.md`, `result.json`,
`reproducibility/`, and five tables:
`enrichment_results.csv`, `enrichment_significant.csv`, `group_summary.csv`,
`ranking_input.csv`, `top_terms.csv`. Python GSEA adds
`tables/gsea_running_scores.csv` when running curves can be built.
`figure_data/` mirrors plot tables. Figures depend on available terms.
GSVA uses `tables/gsva_r_scores.csv` and `figures/gsva_r_heatmap.png` instead.
See `references/output_contract.md` for R-specific files.

## Gotchas

- `result.json.summary.resolved_engine` records the engine actually used.
  The default is now `python`; ask for `--engine auto` to retain auto-selection.
- `tables/enrichment_results.csv` records Python GSEA's local fallback in
  `engine`, with the reason in `result.json.summary.warnings`. This is not
  interchangeable with gseapy's permutation implementation.
- `tables/enrichment_significant.csv` retains the legacy fixed FDR 0.05
  filter. `--fdr-threshold` controls `group_summary.csv` and the report summary.
- `_api.py:37`: `rank_groups` does not infer a suitable matrix. Using scaled `X` can yield
  invalid log-fold changes; use a log-normalised snapshot instead.
- `_api.py:103`: empty gene sets fail validation. Failed R annotation mapping raises an
  error; the R scripts no longer manufacture pathways to fill an empty result.
- `_api.py:205`: GSVA's R database route supports GO_BP and KEGG, not Enrichr's Hallmark
  alias. For Hallmark, explicitly load gene sets and pass the mapping to `gsva`.

## Key CLI

```bash
python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py --demo --output /tmp/sc_enrich_demo
python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py --input clustered.h5ad --output results/ora --gene-set-db hallmark --groupby cell_type
python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py --input clustered.h5ad --output results/gsea --method gsea --gene-sets pathways.gmt --gsea-seed 123
python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py --input clustered.h5ad --output results/gsva --method gsva_r --groupby cell_type --gene-sets pathways.gmt
```

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `rank_groups(adata, *, groupby: str, method: str='wilcoxon') -> pd.DataFrame`

Rank each group's genes against the rest using log-normalised ``X``.

``method`` is wilcoxon (default), t-test or logreg. This uses ``X``, not
``raw``; convert a scaled object with ``adata.raw.to_adata()`` first when
raw holds log-normalised values. Scanpy ranking statistics remain in
``uns``. Return a table with group, gene and available scores/p-values.

### `load_gene_sets(source, *, species: str='human', universe=None) -> dict[str, list[str]]`

Load GMT/JSON or fetch an Enrichr library; optionally match genes to a universe.

``source`` accepts a local path or hallmark/kegg/reactome/go_bp aliases
and full Enrichr library names. Remote sources need network access and
gseapy; local files do not. ``species`` is human (default) or mouse.
Return a term-to-gene-list mapping; no output files are written.

### `demo_gene_sets(*, species: str='human') -> dict[str, list[str]]`

Return the six named PBMC demo signatures, human by default or mouse symbols.

### `marker_gene_sets(markers: pd.DataFrame, *, groups=None, top_n: int | None=100, universe=None) -> dict[str, list[str]]`

Convert marker groups to gene sets, sorted by adjusted p-value or score.

``markers`` needs group and names (or gene). ``groups=None`` selects all;
``top_n=None`` keeps all genes. ``universe`` optionally restricts and
canonicalises gene symbols. Raise ValueError when no sets remain.

### `ora(ranking: pd.DataFrame, gene_sets, *, background=None, engine: str='python', padj_cutoff: float=0.05, log2fc_cutoff: float=0.25, max_genes: int=200, source: str='custom', library_mode: str='local', n_top: int=18) -> pd.DataFrame`

Test over-representation with a local hypergeometric test or clusterProfiler.

``ranking`` accepts marker/DE columns and optional group (default all).
``background=None`` uses every ranked gene; pass all tested genes to make
the universe explicit. Positive genes passing adjusted p-value <= 0.05
and log2FC >= 0.25 are kept, up to 200 per group, by default. Score-only
rankings keep positive scores. ``engine`` is python (default), r or auto
(R when available). ``source`` and ``library_mode`` label result rows;
``n_top`` controls R's optional plots. Return a sorted enrichment table;
:func:`run_info` returns warnings and the resolved engine.

### `gsea(ranking: pd.DataFrame, gene_sets, *, engine: str='python', ranking_metric: str='auto', min_size: int=5, max_size: int=500, permutation_num: int=100, weight: float=1.0, random_state: int=123, source: str='custom', library_mode: str='local', n_top: int=18, species: str='human', gene_set_db: str | None=None) -> pd.DataFrame`

Run preranked GSEA and return sorted terms with NES, p-values and leading edges.

``engine`` is python (default), r (clusterProfiler GMT), auto, or gsea_r
(the retained annotation-database R bridge; pass ``gene_sets=None`` and
select GO_BP, KEGG or Reactome with ``gene_set_db``). Python uses gseapy
when available and reports its existing local rank-based fallback.
``ranking_metric='auto'`` chooses stat, scores or logfoldchanges.
Defaults: gene-set sizes 5..500, 100 permutations, weight 1.0, seed 123.
Permutation count and weight configure Python; the retained R bridge
uses fgsea's multilevel defaults and exponent 1.
``source``/``library_mode`` label rows; ``n_top`` controls R plot selection;
``species`` selects human or mouse annotation for gsea_r. Seeds are passed
to Python and R. No gene sets are fabricated when input or mapping fails.

### `gsva(adata, gene_sets, *, groupby: str, species: str='human', gene_set_db: str='GO_BP', method: str='gsva', min_size: int=5, max_size: int=500) -> pd.DataFrame`

Score mean log-normalised expression per group with R GSVA, returning a long table.

Supply a term-to-genes mapping, or None for the retained GO_BP/KEGG R
annotation bridge selected by ``gene_set_db`` and human/mouse ``species``.
``method`` is gsva (default), ssgsea or zscore; gene-set size defaults are
5..500. R runs serially in a temporary directory. Missing annotation or
gene sets raises an error rather than producing synthetic pathways.

### `run_info(results: pd.DataFrame, *, keep: bool=True) -> dict`

Return a JSON-serialisable diagnostics summary, excluding rankings and R artifacts.

### `top_terms(results: pd.DataFrame, *, n_top: int=18, per_group: int=3) -> pd.DataFrame`

Select up to n_top terms, first reserving per_group rows for each group.

### `group_summary(enrich_df: pd.DataFrame, *, fdr_threshold: float=0.05) -> pd.DataFrame`

Summarise term counts, FDR-significant terms and the top term per group.

### `top_terms_figure(results: pd.DataFrame, *, n_top: int=18)`

Return a horizontal score bar Figure; the caller saves and closes it.

<!-- api:end -->

## See also

`sc-markers` and `sc-de` provide rankings. `marker_gene_sets` can convert their
tables into a signature library; avoid circular validation against the same
cells used to select the markers. CLI flags are in `references/parameters.md`.

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`adjustText`, `anndata`, `gseapy`, `matplotlib`, `networkx`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
