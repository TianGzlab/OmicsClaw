---
name: proteomics-de
description: Load when computing two-group differential protein abundance (group2 vs group1, log2FC +
  p-value + BH-adjusted FDR) via Welch t-test, equal-variance t-test, or Mann-Whitney on a wide protein
  × sample CSV. Skip when you need multi-condition DE (run pairwise contrasts manually); label-based TMT
  linear-mixed models.
trigger: differential abundance, protein expression, MSstats, limma, volcano
tags:
- proteomics
- differential-expression
- ttest
- welch
- mann-whitney
- bh-fdr
---

# proteomics-de

## When to use

ttest is the CLI default; welch and mann_whitney are alternatives. Groups default to the first and second half of columns.
Use existing search-engine tables; this skill does not search raw spectra.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('proteomics-de')
data = library.demo_data(random_state=42)
result = library.differential_abundance(data)
write_output(result, 'tables/differential_abundance.csv')
```

For real data, use `read_input` and pass any `read_table` helper as `reader=`.
The executable `examples/example_step.py` also checks the result and writes a Figure.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `differential_abundance(data: pd.DataFrame, *, group1: list | None=None, group2: list | None=None, method: str='ttest') -> pd.DataFrame`

Compare groups and return a new table with group2-minus-group1 log2 fold changes.

:param data: Protein-indexed, sample-column linear intensities; nonpositive values are missing.
:param group1: First group columns; None uses the first half as in the CLI.
:param group2: Second group columns; None uses the second half as in the CLI.
:param method: CLI default ttest; welch uses unequal variance and mann_whitney tests ranks.
:returns: Per-protein statistics and BH-adjusted p values.
:raises ValueError: Groups overlap, are empty, or the protein index is not unique.

### `significant(results: pd.DataFrame, *, alpha: float=0.05, log2fc_threshold: float=0.0) -> pd.DataFrame`

Select significant proteins from an existing comparison.

:param results: Differential abundance results with padj and log2fc.
:param alpha: CLI default 0.05; strict upper bound on BH-adjusted p values.
:param log2fc_threshold: CLI default 0 disables the absolute fold-change filter.
:returns: A new table retaining selected rows.
:raises ValueError: Thresholds are outside their allowed ranges.

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Read comparison diagnostics.

:param table: Output of differential_abundance.
:param keep: True preserves attrs; False removes diagnostics.
:returns: A separate diagnostic dictionary.
:raises TypeError: The input is not a DataFrame.

### `volcano_figure(results: pd.DataFrame)`

Plot log2 fold change against adjusted significance.

:param results: Differential abundance results.
:returns: A matplotlib Figure without writing files.
:raises KeyError: log2fc or padj is absent.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Generate synthetic intensities with two ordered groups.

:param random_state: CLI seed 42; change for another simulation.
:returns: Protein rows and five control then five treatment columns.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

ttest is the CLI default; welch and mann_whitney are alternatives. Groups default to the first and second half of columns.
Functions return new DataFrames. `run_info(result)` reads diagnostic attrs;
use `keep=False` before serialization when those attrs are not needed.

## Gotchas

- differential_abundance reports group2 minus group1. Nonpositive intensities do not enter the tests. significant uses BH-adjusted p values.
- `demo_data` uses seed 42, matching the CLI; every demo is synthetic.
- `run_info` lives in DataFrame attrs and is not preserved by CSV serialization.

## Inputs and outputs

The CLI reads CSV tables and writes:

- tables/differential_abundance.csv
- tables/significant.csv
- report.md
- result.json
- `reproducibility/commands.sh` records the CLI invocation template.

Functions return data and Figures without writing files. Steps own their outputs.
Demo mode also writes its synthetic input when the original CLI used a file.

## CLI

```bash
python skills/proteomics/proteomics-de/proteomics_de.py --demo --output /tmp/proteomics_de
```

For real input replace `--demo` with `--input <table>`.


## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`
- `proteomics-data-import` for protein-table normalization; `proteomics-de` for comparisons.

## Dependencies

`numpy`, `pandas`, `matplotlib`, `scipy`
