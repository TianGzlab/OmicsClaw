---
name: bulkrna-splicing
description: Load when summarising rMATS / SUPPA2 alternative-splicing output and identifying significant
  differential splicing events. Skip when you only have count-level DE (use bulkrna-de); splicing in single-cell;
  spatial data (currently unsupported).
trigger: alternative splicing, splicing analysis, PSI, rMATS, SUPPA2, exon skipping, differential splicing
tags:
- bulkrna
- splicing
- alternative-splicing
- PSI
- rMATS
- SUPPA2
---

# bulkrna-splicing

## When to use

Summarize existing splicing tests; this skill does not call rMATS or SUPPA2. See the description for adjacent skills.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("bulkrna-splicing")
# Supply DataFrames read with read_input(..., reader=...) for your CSV layout.
result = library.summarize(events)
write_output(result, "tables/result.csv")
```

The synthetic worked step is in `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `summarize(events, *, dpsi_cutoff=0.1, padj_cutoff=0.05)`

Summarize upstream event tests without changing the table.

:param events: DataFrame with gene, event_type, delta_psi and padj columns.
:param dpsi_cutoff: CLI default 0.1; absolute delta-PSI must exceed it.
:param padj_cutoff: CLI default 0.05; adjusted p values must be below it.
:returns: Copy of events with diagnostics in attrs.
:raises ValueError: Required columns, probabilities or thresholds are invalid.

### `run_info(result, *, keep=True)`

Read event counts and threshold diagnostics.

:param result: DataFrame returned by summarize.
:param keep: Default True; False removes diagnostic attrs.
:returns: Diagnostic dictionary, empty after removal.

### `significant_events(result)`

Return events passing both strict thresholds.

:param result: DataFrame returned by summarize, with diagnostics retained.
:returns: New filtered DataFrame.
:raises KeyError: Diagnostics are absent.

### `volcano_figure(result)`

Plot delta-PSI against upstream adjusted significance.

:param result: Event table with delta_psi and padj.
:returns: A matplotlib Figure, without writing files.
:raises KeyError: Required columns are absent.

<!-- api:end -->

## Methods and parameters

See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `summarize` uses strict `abs(delta_psi) > dpsi_cutoff` and `padj < padj_cutoff`.
- Rename upstream columns to `gene`, `event_type`, `delta_psi`, `padj`; `summarize` rejects missing fields.
- `significant_events` filters supplied p values; it does not estimate significance.

## Inputs and outputs

The library returns objects without file writes. CLI inventory:

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/significant_events.csv`
- `tables/splicing_events.csv`
- `figures/dpsi_distribution.png`
- `figures/event_type_distribution.png`
- `figures/volcano_splicing.png`
- `report.md`
- `result.json`

## CLI

```bash
python skills/bulkrna/bulkrna-splicing/bulkrna_splicing.py --demo --output /tmp/bulkrna-splicing
```

## See also

- [Output contract](references/output_contract.md)

## Dependencies

`matplotlib`, `numpy`, `pandas`, `scipy`
