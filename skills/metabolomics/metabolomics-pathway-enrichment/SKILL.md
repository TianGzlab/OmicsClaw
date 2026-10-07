---
name: metabolomics-pathway-enrichment
description: Load when running metabolite-name ORA against an explicit local pathway reference with BH-FDR;
  bundled pathway sets are for explicit demonstrations only. Skip m/z annotation (use metabolomics-annotation)
  and topology analysis or online pathway retrieval (use external mummichog / FELLA or database tools).
trigger: metabolomics pathway, KEGG, MetaboAnalyst, enrichment, mummichog
tags:
- metabolomics
- pathway
- enrichment
- ora
- fisher
- demo
---

# metabolomics-pathway-enrichment

## When to use

Run metabolite-name ORA against explicit pathways or nine demo pathways. External mummichog/FELLA are required for their own methods.

## Use from a step

```python
import pandas as pd
import json
from pathlib import Path
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("metabolomics-pathway-enrichment")
data = read_input('features.csv', reader=pd.read_csv)
pathways = read_input('pathways.json', reader=lambda path: json.loads(Path(path).read_text()))
result = library.enrich(data['metabolite'], pathways=pathways)
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs a seeded synthetic
example through the step runner and writes a table and Figure. Computations
return new DataFrames, leave the input unchanged and expose diagnostics through
`run_info(result)`. Plotting functions write no files.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `enrich(data, *, method='ora', pathways=None)`

Test case-insensitive exact metabolite-name overlap by hypergeometric ORA.

:param data: Iterable of metabolite names; duplicates count once in each overlap.
:param method: CLI default ora, the only implemented method.
:param pathways: Required mapping of pathway names to metabolites lists and kegg_id labels; use demo_pathways() only for demonstrations.
:returns: A new table; BH FDR covers pathways with at least one hit, matching the CLI.
:raises ValueError: A requested method is unimplemented or reference is empty.

### `demo_pathways()`

Return an independent copy of the nine illustrative pathway sets.

:returns: A mapping for explicit demo use, not a complete pathway database.

### `run_info(data, *, keep=True)`

Read diagnostics attached to a returned table.

:param data: DataFrame returned by this library.
:param keep: Default True; use False in the CLI to remove diagnostics.
:returns: An independent dictionary describing the run.
:raises ValueError: The table carries no run_info.

### `enrichment_figure(data, *, n_top=10)`

Plot the strongest pathway overlaps by adjusted p value.

:param data: Results returned by enrich.
:param n_top: Default 10; maximum number of pathways shown.
:returns: A matplotlib Figure.
:raises KeyError: pathway or fdr is absent.

<!-- api:end -->

## Methods and parameters

Matching is case-insensitive exact name equality, not substring matching. The background is the union of reference members. Hypergeometric survival probabilities and BH correction apply to pathways with at least one hit, matching the legacy CLI.

## Gotchas

- `enrich` requires explicit `pathways=` and implements only ora. Missing reference data and fella/mummichog requests fail. `demo_pathways()` explicitly selects the nine illustrative sets; never use these as biological evidence.
- `tables/pathway_enrichment.csv` has a stable schema even with no overlap. `result.json` records the reference scope in `data.run_info.reference_scope`.

## Inputs and outputs

CSV input; `tables/pathway_enrichment.csv`, `report.md` and `result.json`. Demo mode also writes its synthetic input CSV at the output root.
Real input also requires a JSON reference: `{"pathway name": {"kegg_id": "identifier", "metabolites": ["glucose", "pyruvate"]}}`.
The function library returns objects; the CLI and step own file writes.

## CLI

```bash
python skills/metabolomics/metabolomics-pathway-enrichment/met_pathway.py --demo --output /tmp/metabolomics_pathway_enrichment
python skills/metabolomics/metabolomics-pathway-enrichment/met_pathway.py --input features.csv --pathway-file pathways.json --output /tmp/metabolomics_pathway_real
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`numpy`, `pandas`, `scipy`, `matplotlib`
