---
name: bulkrna-geneid-mapping
description: Load when converting Ensembl, Entrez or symbol IDs in a bulk RNA count matrix using an explicit mapping or a small human demo reference. Skip when IDs already match downstream needs; use fetch_mapping explicitly for MyGene lookup.
trigger: gene ID, Ensembl, Entrez, gene symbol, ID mapping, gene annotation, convert IDs
tags:
- bulkrna
- gene-id
- mapping
- Ensembl
- Entrez
- HGNC
- annotation
---

# bulkrna-geneid-mapping

## When to use

Convert Ensembl, Entrez and symbol identifiers in count-matrix row indexes. Use a caller-provided mapping for full coverage or non-human organisms. Skip when identifiers already match downstream needs.

## Use from a step

```python
import pandas as pd
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill('bulkrna-geneid-mapping')
data = read_input('counts.csv', reader=lambda path: pd.read_csv(path, index_col=0))
result = library.map_ids(data)
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs offline and supports
fresh-kernel replay. Pure computations return objects; CLI and steps own writes.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `map_ids(data, *, from_type='ensembl', to_type='symbol', species='human', on_duplicate='sum', mapping=None)`

Map count-matrix row identifiers without network or file access.

:param data: Gene-by-sample counts; the row index contains source IDs.
:param from_type: CLI default ensembl; entrez and symbol are also supported.
:param to_type: CLI default symbol; target namespace.
:param species: CLI default human; mouse requires an explicit reference.
:param on_duplicate: CLI default sum; first or drop resolve target collisions differently.
:param mapping: Optional source/target DataFrame; None uses ten human demo genes only.
:returns: A new mapped DataFrame with reference scope, mapping records and summary diagnostics.
:raises ValueError: Namespaces, duplicate policy or reference data are invalid.

### `fetch_mapping(data, *, from_type='ensembl', to_type='symbol', species='human')`

Query MyGene explicitly and return a local source/target mapping table.

:param data: Iterable of identifiers to send to the public MyGene service.
:param from_type: Default ensembl; source namespace.
:param to_type: Default symbol; requested target namespace.
:param species: Default human; MyGene species selector.
:returns: A DataFrame containing only identifiers for which MyGene returned a match.
:raises ImportError: Install mygene with install_skill_deps if unavailable.
:raises Exception: Network or service errors propagate; no demo substitute is returned.

### `mapping_table(data)`

Return the original-to-target mapping decisions for every input row.

:param data: Mapped count matrix returned by map_ids.
:returns: A new DataFrame with original_id, stripped_id, mapped_id and was_mapped.
:raises KeyError: The count matrix has no mapping diagnostics.

### `run_info(data, *, keep=True)`

Read mapping diagnostics without modifying the count values.

:param data: Mapped counts returned by map_ids.
:param keep: Default True; the CLI removes diagnostics with False.
:returns: An independent diagnostic dictionary.
:raises TypeError: data is not a DataFrame.

### `mapping_figure(data)`

Plot mapped and unmapped source-row counts.

:param data: Count matrix returned by map_ids.
:returns: A matplotlib Figure; no files are written.
:raises KeyError: Mapping diagnostics are absent.

<!-- api:end -->

## Methods and parameters

Local map_ids never queries the network. Its default reference contains ten human genes; it also supports reverse namespace mapping within that small reference. Pass a source/target DataFrame to override it. fetch_mapping explicitly sends identifiers to MyGene. The CLI queries MyGene only with --fetch-mygene.

## Gotchas

- `map_ids` strips Ensembl version suffixes, retains unmapped identifiers and resolves target collisions with sum, first or drop. Explicit mappings take priority. Non-human mapping without a reference raises an error. `run_info` identifies demo versus provided reference scope.

## Inputs and outputs

`tables/mapped_counts.csv`, `tables/mapping_table.csv`, `report.md`, `result.json` and `reproducibility/commands.sh`. `tables/unmapped_genes.csv` is conditional on unmapped input rows. The CLI does not write figures.

## CLI

```bash
python skills/bulkrna/bulkrna-geneid-mapping/bulkrna_geneid_mapping.py --demo --output /tmp/bulkrna_geneid_mapping
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`numpy`, `pandas`, `mygene`, `matplotlib`
