---
name: bulkrna-coexpression
description: Load when discovering bulk gene co-expression modules and hub genes with R WGCNA. Skip direct expression contrasts (use bulkrna-de), existing-gene-list PPI lookup (use bulkrna-ppi-network), or single-cell networks (use sc-grn).
trigger: coexpression, WGCNA, gene network, co-expression modules, hub genes, gene modules
tags:
- bulkrna
- coexpression
- WGCNA
- network
- modules
- hub-genes
---

# bulkrna-coexpression

## When to use

Load when discovering bulk gene co-expression modules and hub genes with R WGCNA. Skip direct expression contrasts (use bulkrna-de), existing-gene-list PPI lookup (use bulkrna-ppi-network), or single-cell networks (use sc-grn).

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill("bulkrna-coexpression")
result = library.analyze(data, power=6, min_module_size=10)
write_output(result, "tables/result.csv")
write_output(library.module_sizes_figure(result), "figures/result.png")
```

Read expression and metadata with `read_input` before calling the library.
`examples/example_step.py` constructs a small synthetic dataset and checks
its results through the step runner and fresh-kernel replay.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `analyze(data: pd.DataFrame, *, power: int | None=None, min_module_size: int=10, random_state: int=54321) -> pd.DataFrame`

Return R WGCNA gene-module assignments, leaving expression unchanged.

:param data: Nonnegative feature-by-sample expression; provide normalized data on the intended correlation scale.
:param power: CLI default None selects the soft threshold; set a positive integer to override it.
:param min_module_size: CLI default 10 genes per module.
:param random_state: WGCNA blockwiseModules default seed 54321; fixes its preclustering.
:returns: Gene/module DataFrame with diagnostics, hub genes and threshold fit in attrs.
:raises ValueError: Input, sample count, power or module size is invalid.
:raises ImportError: R WGCNA or Matrix is unavailable.
:raises RuntimeError: R analysis fails.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return WGCNA method diagnostics and summary.

:param data: Result from analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Independent diagnostics dictionary.
:raises ValueError: No WGCNA diagnostics are present.

### `threshold_fit(data: pd.DataFrame) -> pd.DataFrame`

Return the signed scale-free fit for each tested soft threshold.

:param data: Result from analyze.
:returns: Table containing power, r_squared and mean_connectivity.
:raises ValueError: No fit table is stored.

### `hub_genes(data: pd.DataFrame) -> pd.DataFrame`

Return the highest absolute module-membership genes per non-grey module.

:param data: Result from analyze.
:returns: Table with gene, module and kME columns.
:raises ValueError: No hub table is stored.

### `module_sizes_figure(data: pd.DataFrame)`

Plot assignment counts, including grey unassigned genes.

:param data: Gene/module table from analyze.
:returns: Matplotlib Figure.
:raises ValueError: The module column is missing.

<!-- api:end -->

## Methods and parameters

The function library returns DataFrames and Figures. The CLI loads the
same library and owns reports and file writes. R runs in a temporary
directory using Matrix Market, feature/sample identifiers and metadata.
No R intermediate is a permanent CLI output.

## Gotchas

- `analyze` requires R WGCNA and Matrix, at least eight samples, and finite nonnegative expression. Cohorts with fewer than 15 samples emit a warning.
- `analyze(power=None)` selects a soft threshold; an explicit power is honored. Integer matrices are converted to double for WGCNA.
- `run_info()["filtered_genes"]` lists genes removed by WGCNA quality checks. Grey is unassigned; module IDs are color strings.
- `hub_genes` ranks absolute module membership within each non-grey module. This is correlation evidence, not proof of regulation.
- `threshold_fit` reports signed scale-free R-squared and connectivity. The correlation analysis uses the supplied expression scale; normalize upstream as needed.
- `analyze(random_state=54321)` preserves the WGCNA default seed and uses one R thread. No Python module-detection fallback is used.

## Inputs and outputs

Expression CSV with genes in the first column and samples in the remaining columns. The API takes that gene column as the DataFrame index.

CLI outputs:

- `tables/module_assignments.csv`
- `tables/hub_genes.csv`
- `tables/threshold_fit.csv`
- `figures/scale_free_fit.png`
- `figures/module_sizes.png`
- `figures/module_dendrogram.png` (assignment overview, not a dendrogram)
- `report.md`, `result.json`
- `reproducibility/commands.sh`

## CLI

```bash
python skills/bulkrna/bulkrna-coexpression/bulkrna_coexpression.py --demo --output /tmp/bulkrna_coexpression_demo
```

Run the script with `--help` for real-input arguments.

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`matplotlib`, `numpy`, `pandas`, `scipy`, `WGCNA`, `Matrix`
