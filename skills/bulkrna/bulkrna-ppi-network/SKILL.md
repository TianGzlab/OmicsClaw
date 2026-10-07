---
name: bulkrna-ppi-network
description: Load when querying STRING for the protein-protein interaction neighborhood of a bulk
  RNA-seq DEG list and finding hub genes. Skip when pathway enrichment of the same list (use bulkrna-enrichment);
  de novo co-expression network discovery (use bulkrna-coexpression).
trigger: PPI, protein interaction, STRING, network, hub gene, interactome
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

Analyze a PPI subgraph and rank hub genes from explicit interaction tables. Use bulkrna-coexpression for expression-derived networks and bulkrna-enrichment for pathways.

## Use from a step

```python
import pandas as pd
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill('bulkrna-ppi-network')
data = read_input('edges.csv', reader=pd.read_csv)
result = library.analyze(data)
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs offline and supports
fresh-kernel replay. Pure computations return objects; CLI and steps own writes.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `analyze(data, *, genes=None, induced=False)`

Rank query nodes using the CLI's unweighted neighborhood convention.

:param data: Interaction DataFrame with gene_a, gene_b and score columns; scores do not weight centrality.
:param genes: Optional gene list including isolates; None uses all edge endpoints.
:param induced: Default False preserves external neighbors in degree/closeness; True restricts edges to genes.
:returns: A node-centrality DataFrame with degree, betweenness, closeness and hub_score.
:raises ValueError: Edge columns or the node list are invalid.

### `fetch_interactions(data, *, species=9606, score_threshold=400)`

Query STRING explicitly; unavailable or malformed responses raise.

:param data: Gene identifiers sent to the public STRING service.
:param species: CLI default 9606 (human); NCBI taxonomy identifier.
:param score_threshold: CLI default 400; integer confidence cutoff from 0 to 1000.
:returns: A DataFrame with gene_a, gene_b and scores on STRING's 0 to 1 scale.
:raises ImportError: Install requests with install_skill_deps if unavailable.
:raises ValueError: Parameters or response columns are invalid.
:raises Exception: Network and HTTP failures propagate without demo fallback.

### `run_info(data, *, keep=True)`

Read topology diagnostics attached to the node table.

:param data: Centrality DataFrame returned by analyze.
:param keep: Default True; the CLI removes diagnostics with False.
:returns: An independent summary dictionary.
:raises TypeError: data is not a DataFrame.

### `network_figure(data, *, genes=None, random_state=42)`

Draw a seeded spring layout without changing numpy's global random state.

:param data: Edge DataFrame accepted by analyze.
:param genes: Optional gene list including isolates; None uses edge endpoints.
:param random_state: CLI default 42; spring-layout initialization seed.
:returns: A matplotlib Figure.
:raises ValueError: Edges or node list are invalid.

### `hubs_figure(data, *, top_n=20)`

Plot the highest-ranked hub scores.

:param data: Centrality table returned by analyze.
:param top_n: CLI default 20; maximum number of nodes shown.
:returns: A matplotlib Figure.
:raises KeyError: gene or hub_score is absent.

<!-- api:end -->

## Methods and parameters

fetch_interactions explicitly queries STRING with a 0 to 1000 confidence threshold and returns 0 to 1 scores. analyze uses an unweighted graph and includes provided isolates. Hub scores combine normalized degree and betweenness. The CLI demo reads the fixed 364-edge STRING table described in data/README.md; it does not contact STRING.

## Gotchas

- `--demo` accepts only species 9606 because `data/demo_string_edges.csv` contains human interactions; other species require a real query.
- `fetch_interactions` propagates HTTP/network errors and never substitutes demo edges. `analyze` defaults to the CLI neighborhood convention: degree includes external neighbors, closeness visits them, and betweenness is restricted to query nodes. Use induced=True to restrict all edges to the query set. `network_figure` draws query nodes only and uses seed 42 without changing the global random generator.

## Inputs and outputs

`tables/hub_genes.csv`, `tables/interaction_edges.csv`, `tables/node_centrality.csv`, `figures/hub_genes_barplot.png`, `figures/ppi_network.png`, `report.md`, `result.json` and `reproducibility/commands.sh`.

## CLI

```bash
python skills/bulkrna/bulkrna-ppi-network/bulkrna_ppi_network.py --demo --output /tmp/bulkrna_ppi_network
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`numpy`, `pandas`, `matplotlib`, `requests`
