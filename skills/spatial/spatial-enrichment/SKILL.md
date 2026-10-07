---
name: spatial-enrichment
description: Load when running pathway or gene-set enrichment per cluster on spatial AnnData with over-representation, preranked GSEA, or ssGSEA group-mean scores. Skip when ranking spatially variable genes (use spatial-genes) or comparing conditions (use spatial-condition).
trigger: pathway enrichment, gene set enrichment, enrichr, GSEA, ssGSEA, GO, Reactome, MSigDB
tags:
- spatial
- enrichment
- pathway
- gsea
- ssgsea
- enrichr
- gene-set
---

# spatial-enrichment

## When to use

Interpret group markers with gene sets, or score group-mean expression.
The default is a small local OmicsClaw signature library. Hosted libraries
require network access; explicit gene-set mappings and local GMT/JSON files
work offline. Synthetic demo signatures are not curated biological pathways.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-enrichment")
adata = read_input("processed.h5ad")
library.enrich(adata, groupby="leiden", source="omicsclaw_core")
write_output(library.results(adata), "tables/enrichment_results.csv")
```

The executable example uses explicit synthetic marker sets and checks their
known group enrichment.

For local libraries use `sets = read_input("data/sets.gmt", reader=library.read_gene_sets)`,
then `library.enrich(adata, gene_sets=sets)`. `read_input` records the file hash.
`library.fetch_gene_sets("KEGG_2021_Human")` explicitly accesses the network.
Cache that mapping as JSON before a repeatable analysis, then load the cached
file with `read_input` and this reader. Computation accepts built-in sources or mappings.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `read_gene_sets(path)`

Read a local GMT or JSON gene-set library without writing files.

In a step call read_input(path, reader=library.read_gene_sets) to record
the input file hash and resolve the path relative to the project root.

:param path: Local GMT or JSON path supplied by read_input or the CLI.
:returns: Term-to-gene mapping retaining its local source metadata.
:raises FileNotFoundError: The local file is absent.
:raises ValueError: The format or JSON structure is invalid.

### `fetch_gene_sets(source, *, species='human')`

Fetch a remote Enrichr library; this call requires network access.

Cache the mapping as JSON, then use read_input(path, reader=library.read_gene_sets)
for repeatable analysis steps. Fetching alone does not record a file hash.

:param source: Enrichr library name or an alias in references/parameters.md.
:param species: Default human; mouse is also supported.
:returns: Term-to-gene mapping retaining requested and resolved library names.
:raises ValueError: Species or remote source is invalid or unavailable.
:raises ImportError: gseapy is unavailable; use install_skill_deps.

### `enrich(adata, *, method='enrichr', groupby='leiden', source='omicsclaw_core', species='human', gene_sets=None, gene_set=None, fdr_threshold=0.05, n_top_terms=20, random_state=123, **parameters)`

Enrich group markers or score group means and return the same AnnData.

Marker ranking reads raw when present, otherwise X; ssGSEA reads X and
scores group means, then copies each group's score to its observations.

:param adata: Log-normalized expression and group labels; modified in place.
:param method: CLI default enrichr; gsea or ssgsea also supported.
:param groupby: CLI default leiden; obs column defining groups.
:param source: CLI default omicsclaw_core; only built-in libraries are resolved here.
:param species: CLI default human; mouse changes the built-in symbols.
:param gene_sets: Already-read term-to-gene mapping; None selects the built-in source.
:param gene_set: Optional built-in library alias overriding source.
:param fdr_threshold: CLI default 0.05 adjusted significance cutoff.
:param n_top_terms: CLI default 20 reported terms or attached score columns.
:param random_state: CLI default 123 for GSEA and ssGSEA backend randomness.
:param parameters: Method-specific CLI options in references/parameters.md.
:returns: The same AnnData, with canonical enrichment_results in uns.
:raises ValueError: Groups, gene sets or numeric thresholds are invalid.
:raises TypeError: A file path is passed; use read_gene_sets first.

### `results(adata, *, significant_only=False)`

Return enrichment results, retaining missing p values for score-only methods.

:param adata: AnnData returned by enrich.
:param significant_only: Default False; True selects adjusted p values below FDR.
:returns: A new DataFrame; ssGSEA scores do not imply significance.
:raises ValueError: No enrichment run is recorded.

### `run_info(adata, *, keep=True)`

Read enrichment diagnostics, including any executed fallback method.

:param adata: AnnData returned by enrich.
:param keep: Default True; False removes transient diagnostics for CLI output.
:returns: Diagnostic dictionary, including enrich_df and marker_df.
:raises ValueError: No enrichment run is recorded.

### `terms_figure(adata, *, n_top=20)`

Plot available term scores without treating scores as calibrated p values.

:param adata: AnnData returned by enrich.
:param n_top: Default 20 rows, matching the CLI report size.
:returns: A matplotlib Figure; an empty result is labelled explicitly.
:raises ValueError: No run is recorded or n_top is not positive.

<!-- api:end -->

## Methods and parameters

Enrichr performs local over-representation on positive markers; GSEA uses
per-group rankings. ssGSEA scores group means and copies each score to its
spots. These are not independent per-spot estimates.
Defaults include 100 GSEA permutations and seed 123. See
[parameters](references/parameters.md) for keyword arguments and
[methodology](references/methodology.md) for scoring details.

## Gotchas

- `run_info()` records warnings and the executed method if GSEApy falls back
  to hypergeometric, mean-rank permutation or descriptive mean scoring.
- `fetch_gene_sets` raises when a requested remote library cannot be resolved.
- `uns['enrichment_score_columns']` lists attached ssGSEA columns.
- `results(significant_only=True)` excludes rows without p values.
- `enrich` requires group labels; automatic Leiden clustering belongs to the CLI.

## Inputs and outputs

The library reads log-normalized expression; Scanpy marker ranking prefers
raw if present. Functions modify AnnData and return tables/Figures. The CLI
writes `processed.h5ad`, `tables/enrichment_results.csv`, diagnostics, report
and result JSON. See [output contract](references/output_contract.md) for
conditional outputs.

## CLI

```bash
python skills/spatial/spatial-enrichment/spatial_enrichment.py --input processed.h5ad --output results/enrichment
python skills/spatial/spatial-enrichment/spatial_enrichment.py --demo --output /tmp/enrichment_demo
```

## See also

Use spatial-de for markers, spatial-genes for autocorrelation, or sc-enrichment
for non-spatial data.

## Dependencies

`anndata`, `gseapy`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
