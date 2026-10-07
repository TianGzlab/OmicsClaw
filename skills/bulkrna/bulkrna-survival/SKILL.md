---
name: bulkrna-survival
description: Load when comparing bulk expression strata against clinical time-to-event data with Kaplan-Meier and log-rank tests. R survival also fits Cox HR; Python reports a descriptive events/person-time ratio. Skip missing clinical outcomes.
trigger: survival, Kaplan-Meier, Cox, prognosis, hazard ratio, overall survival, clinical outcome
tags:
- bulkrna
- survival
- Kaplan-Meier
- Cox
- hazard-ratio
- clinical
---

# bulkrna-survival

## When to use

Load when comparing bulk expression strata against clinical time-to-event data with Kaplan-Meier and log-rank tests. R survival also fits Cox HR; Python reports a descriptive events/person-time ratio. Skip missing clinical outcomes.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill("bulkrna-survival")
result = library.analyze(data, clinical=clinical, backend="python")
write_output(result, "tables/result.csv")
write_output(library.curve_figure(result, gene="G"), "figures/result.png")
```

Read expression and metadata with `read_input` before calling the library.
`examples/example_step.py` constructs a small synthetic dataset and checks
its results through the step runner and fresh-kernel replay.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `analyze(data: pd.DataFrame, *, clinical: pd.DataFrame, genes: list[str] | None=None, cutoff_method: str='median', backend: str='auto') -> pd.DataFrame`

Return gene-wise survival comparisons without modifying expression.

:param data: Nonnegative feature-by-sample expression.
:param clinical: Clinical table with unique sample, nonnegative time and binary event columns.
:param genes: Genes to test; None uses every row. Missing genes raise.
:param cutoff_method: CLI default median; optimal scans cuts with unadjusted p-values.
:param backend: auto prefers R survival with Cox HR, as the CLI did; python uses an events/person-time ratio.
:returns: Per-gene table with diagnostics and KM points attached in attrs.
:raises ValueError: Identifiers, clinical values, requested genes or comparison groups are invalid.
:raises ImportError: Explicit R backend lacks survival or Matrix.
:raises RuntimeError: The requested R method fails or returns incomplete results.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return actual backend, HR estimator and summary.

:param data: Result from analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Diagnostics dictionary.
:raises ValueError: The table has no analysis diagnostics.

### `km_table(data: pd.DataFrame) -> pd.DataFrame`

Return the fitted Kaplan-Meier points for both expression strata.

:param data: Result from analyze.
:returns: New table with gene, group, time and survival columns.
:raises ValueError: The result lacks stored curves.

### `curve_figure(data: pd.DataFrame, *, gene: str)`

Plot the stored Kaplan-Meier curves for one analyzed gene.

:param data: Result from analyze.
:param gene: Exact gene identifier in the result.
:returns: Matplotlib Figure.
:raises ValueError: No curve exists for the requested gene.

<!-- api:end -->

## Methods and parameters

The function library returns DataFrames and Figures. The CLI loads the
same library and owns reports and file writes. R runs in a temporary
directory using Matrix Market, feature/sample identifiers and metadata.
No R intermediate is a permanent CLI output.

## Gotchas

- `analyze(backend="auto")` prefers R survival, which fits Cox PH hazard ratios. Its Python fallback uses a descriptive events/person-time ratio. `run_info()["hazard_estimator"]` distinguishes them.
- `analyze` raises for missing genes or insufficient high/low groups; it does not silently deliver a subset of the requested genes.
- `analyze(cutoff_method="optimal")` scans cutoffs and reports unadjusted p-values. Treat the selected-cutoff test as exploratory.
- `km_table` exposes both KM curves. Median survival is None when a curve never reaches 0.5; no extrapolated median is invented.
- `run_info()["dropped_expression_samples"]` reports samples excluded by the expression/clinical intersection. Clinical IDs must be unique.

## Inputs and outputs

Feature-by-sample expression CSV and a clinical CSV containing unique sample, nonnegative time and binary event.

CLI outputs:

- `tables/survival_results.csv`
- `figures/km_<gene>.png` per successful gene
- `figures/forest_plot.png` when at least two genes succeed
- `report.md`, `result.json`
- `reproducibility/commands.sh`

## CLI

```bash
python skills/bulkrna/bulkrna-survival/bulkrna_survival.py --demo --output /tmp/bulkrna_survival_demo
```

Run the script with `--help` for real-input arguments.

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`matplotlib`, `numpy`, `pandas`, `scipy`, `survival`, `Matrix`
