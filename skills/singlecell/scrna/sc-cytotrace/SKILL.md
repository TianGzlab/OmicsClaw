---
name: sc-cytotrace
description: Load when computing per-cell differentiation potency / stemness scores from gene-expression
  complexity on a scRNA AnnData via the CytoTRACE-simple method. Skip when ordering cells along a trajectory
  (use sc-pseudotime); marker-based cell-type labelling (use sc-cell-annotation).
tags:
- singlecell
- scrna
- cytotrace
- potency
- stemness
- differentiation
---

# sc-cytotrace

## Use from a step

```python
potency = load_skill("sc-cytotrace")
adata = potency.cytotrace(read_input("expression.h5ad"), layer="counts")
write_output(potency.potency_table(adata), "tables/potency.csv")
write_output(potency.potency_figure(adata), "figures/potency.png")
write_output(adata, "intermediate/adata_potency.h5ad")
```

The function annotates the input in place. The PBMC example in
`examples/example_step.py` demonstrates the call, not biological differentiation.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `cytotrace(adata, *, n_neighbors: int=30, layer: str | None=None)`

Annotate a complexity-based potency proxy in place, preserving X.

This is CytoTRACE-simple, not the published CytoTRACE or CytoTRACE 2.
It counts positive expression, smooths rank scores, ranks them again
and bins them into six relative categories. Existing neighbors are reused.

:param adata: AnnData with expression and optionally PCA/neighbors.
:param n_neighbors: Neighbors to construct when absent; default 30.
:param layer: Expression layer for gene detection; None uses X.
    Use counts or unscaled log expression, not centered/scaled X.
:returns: The same AnnData with cytotrace_score, cytotrace_gene_count
    and cytotrace_potency in obs; run_info returns diagnostics.
:raises ValueError: The input is empty, a layer is missing, or neighbors < 1.

### `run_info(adata, *, keep: bool=True) -> dict`

Read JSON potency diagnostics; keep=False removes them from uns.

### `potency_table(adata) -> pd.DataFrame`

Return per-cell score, category and detected-gene count, indexed by cell.

### `potency_composition(adata) -> pd.DataFrame`

Return counts for the six relative potency bins; they are not cell-type calls.

### `potency_figure(adata)`

Return a matplotlib Figure showing the potency score distribution.

<!-- api:end -->

## Methods and parameters

CytoTRACE-simple counts positive expression, rank-normalizes that complexity,
smooths on a neighbor graph, ranks again and assigns six relative bins.
It is not the published CytoTRACE or CytoTRACE 2 model.

`n_neighbors=30` retains the CLI default and is used only if a neighbor graph
must be built. `layer=None` uses X; specify a counts layer or unscaled
log-normalized expression. Computation is deterministic for a fixed graph.

## Gotchas

- The second rank transform makes the six `cytotrace_potency` bins approximately
  equal-sized when scores have no ties. Labels such as Totipotent are names
  of these bins, not evidence that those cells are biologically totipotent (`_api.py:112`).
- Positive values in centered/scaled X do not count detected genes. Use
  `layer="counts"` or an unscaled matrix; inspect `potency_table` (`_api.py:72`).
- Existing neighbors are reused regardless of `n_neighbors`. The CLI's
  processed PBMC demo has scaled X and is retained only for compatibility (`_api.py:80`).
- `run_info(adata)["degenerate"]` marks at most one occupied category. It
  does not raise; the CLI mirrors this under `result.json["summary"]`.

## Inputs & Outputs

Input is AnnData with expression, optionally PCA and neighbors. The API adds
`cytotrace_score`, `cytotrace_potency` and `cytotrace_gene_count` to obs and
returns tables/Figures without writing files.

The CLI writes `processed.h5ad`, `tables/cytotrace_scores.csv`, `report.md`,
`result.json`, `figure_data/cytotrace_embedding.csv` and potency/distribution
plots under `figures/`. R-enhanced plots are optional.

## Key CLI

```bash
python skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py --demo --output /tmp/sc_cytotrace_demo
python skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py --input normalized.h5ad --n-neighbors 30 --output results/
```

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`
