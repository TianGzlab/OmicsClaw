---
name: bulkrna-ppi-network
description: Load when querying STRING for the protein-protein interaction subgraph induced by a bulk RNA-seq DEG list and finding hub genes. Skip for pathway enrichment of the same list (use bulkrna-enrichment) or for de novo co-expression network discovery (use bulkrna-coexpression).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- PPI
- STRING
- network
- hub-genes
- protein-interaction
---

# bulkrna-ppi-network

## When to use

Run after `bulkrna-de` to ask "what does the STRING PPI subgraph
induced by my DEG list look like, and which proteins are central?".
Queries the public STRING API (no installation needed), constructs the
induced subgraph, and ranks hub proteins by degree centrality.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Gene list / DE results | `.csv` (gene names) | yes (or `--demo`) |
| `--species` NCBI taxon | int | default `9606` (human); `10090` for mouse |
| `--score-threshold` | int 0–1000 | default `400` (STRING "medium" confidence) |
| `--top-n` | int | default `20` (top-degree hubs to report) |

| Output | Path | Notes |
|---|---|---|
| Edge list | `tables/interaction_edges.csv` | source / target / score |
| Node centrality | `tables/node_centrality.csv` | per-gene degree / betweenness / closeness / hub_score |
| Hub genes | `tables/hub_genes.csv` | top-N from `node_centrality` by hub_score |
| Network figure | `figures/ppi_network.png` | NetworkX layout |
| Degree distribution | `figures/degree_distribution.png` | scale-free check |
| Report | `report.md` + `result.json` | summary keys: `n_genes`, `n_edges`, `n_connected`, `n_isolated`, `mean_degree` |

## Flow

1. Parse gene list from `--input` (treats first column as gene names).
2. Query STRING API with `species` + `score_threshold`.
3. On API failure, fall back silently to built-in demo edges (`bulkrna_ppi_network.py:118` warns "STRING API failed (...) — using built-in demo edges").
4. Build NetworkX graph; compute degree centrality.
5. Report top-N hubs; render network + degree-distribution figures.

## Gotchas

- **STRING-API-failure fallback is to DEMO edges, not a smaller real query.**  `bulkrna_ppi_network.py:118` catches any API exception and substitutes the built-in toy network.  This means a transient network outage produces output that looks normal but is unrelated to the user's gene list.  The summary dict does not record which edge source ran — grep the run's stderr for "STRING API failed" to detect a silent fallback before reporting downstream conclusions.
- **`--score-threshold` is on STRING's 0–1000 scale, not 0–1.**  Default `400` is STRING's "medium" confidence band; `700` is "high"; `900` is "highest".  Passing `0.4` (a float) is silently coerced to `0` and pulls every edge in the database.
- **`--species` is the NCBI taxon ID** (default `9606` human, `10090` mouse).  Passing the string `"human"` or `"mouse"` raises a type error from `int(args.species)`.  STRING also requires the species to be in its supported list — exotic taxa fail at the API layer.
- **Gene-name namespace must match STRING's expectations.**  STRING uses HGNC symbols for human, MGI symbols for mouse.  Feeding Ensembl IDs gives ~zero hits and a near-empty network — pre-run `bulkrna-geneid-mapping` to convert.

## Key CLI

```bash
python omicsclaw.py run bulkrna-ppi-network --demo
python omicsclaw.py run bulkrna-ppi-network \
  --input de_significant.csv --output results/
python omicsclaw.py run bulkrna-ppi-network \
  --input de_significant.csv --output results/ \
  --species 10090 --score-threshold 700 --top-n 30
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — STRING query format, hub-gene definition (degree centrality)
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-de` (upstream — DEG source), `bulkrna-enrichment` (parallel: pathway view of the same list), `bulkrna-coexpression` (parallel: de novo co-expression network from the count matrix), `bulkrna-geneid-mapping` (run upstream to convert IDs to HGNC/MGI)
