---
name: proteomics-enrichment
description: Load for Fisher over-representation analysis of protein identifiers against caller-supplied pathways. Skip rank-based GSEA (use bulkrna-enrichment) or protein differential testing (use proteomics-de).
trigger: proteomics enrichment, pathway analysis, ORA
tags:
- proteomics
- enrichment
---

# proteomics-enrichment

## When to use

ORA uses one-sided Fisher tests and BH correction. Pass an explicit pathway_db and a background_size matching the measured universe.
Use existing search-engine tables; this skill does not search raw spectra.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('proteomics-enrichment')
data = library.demo_data(random_state=42)
result = library.enrich(data['protein_id'].tolist(), pathway_db=library.demo_pathways())
write_output(result, 'tables/enrichment_results.csv')
```

For real data, use `read_input` and pass any `read_table` helper as `reader=`.
The executable `examples/example_step.py` also checks the result and writes a Figure.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `enrich(genes: list[str], *, pathway_db: dict | None=None, background_size: int | None=None, method: str='ora') -> pd.DataFrame`

Run one-sided Fisher tests with BH correction against an explicit pathway library.

:param genes: Protein or gene identifiers in the same identifier space as pathway_db.
:param pathway_db: Required pathway-to-member mapping; no default biological database is assumed.
:param background_size: CLI default None uses the input/library union plus at least one background-only member.
:param method: CLI default ora is the only implemented method.
:returns: Ranked pathway overlaps, odds ratios and adjusted p values.
:raises ValueError: The library is absent, the method is invalid, or the background is too small.

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Read enrichment diagnostics.

:param table: Output of enrich.
:param keep: True preserves attrs; False removes diagnostics.
:returns: A separate dictionary with library provenance and summary.
:raises TypeError: The input is not a DataFrame.

### `enrichment_figure(table: pd.DataFrame, *, top_n: int=10)`

Plot leading pathways by enrichment ratio.

:param table: Enrichment results sorted by p value.
:param top_n: Display ten pathways by default; change for a larger result table.
:returns: A matplotlib Figure without writing files.
:raises KeyError: pathway or enrichment_ratio is absent.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Generate a synthetic significant-protein list.

:param random_state: CLI seed 42; change for another simulation.
:returns: Eighteen example identifiers with simulated statistics.
:raises ValueError: The seed is invalid.

### `demo_pathways() -> dict`

Return the eight small illustrative pathway sets used by --demo.

:returns: A separate mapping, not a production pathway database.
:raises RuntimeError: No runtime failures are expected.

<!-- api:end -->

## Methods and parameters

ORA uses one-sided Fisher tests and BH correction. Pass an explicit pathway_db and a background_size matching the measured universe.
Functions return new DataFrames. `run_info(result)` reads diagnostic attrs;
use `keep=False` before serialization when those attrs are not needed.

## Gotchas

- enrich requires pathway_db. demo_pathways contains eight illustrative sets and is only for demonstrations. The CLI requires --pathways for non-demo input; --species is recorded only.
- `demo_data` uses seed 42, matching the CLI; every demo is synthetic.
- `run_info` lives in DataFrame attrs and is not preserved by CSV serialization.

## Inputs and outputs

The CLI reads CSV tables and writes:

- tables/enrichment_results.csv
- report.md
- result.json
- `demo_proteins.csv` is written only with `--demo`.

Functions return data and Figures without writing files. Steps own their outputs.
Demo mode also writes its synthetic input when the original CLI used a file.

## CLI

```bash
python skills/proteomics/proteomics-enrichment/prot_enrichment.py --demo --output /tmp/proteomics_enrichment
```

For real input replace `--demo` with `--input <table>`.
Non-demo enrichment also requires `--pathways <pathways.json>`, a pathway-to-members object.

## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`
- `proteomics-data-import` for protein-table normalization; `proteomics-de` for comparisons.

## Dependencies

`numpy`, `pandas`, `matplotlib`, `scipy`
