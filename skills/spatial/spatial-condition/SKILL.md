---
name: spatial-condition
description: Load when comparing conditions on spatial AnnData using biological-sample pseudobulk PyDESeq2 or Wilcoxon, with sample, condition and cluster labels. Skip one-condition per-cluster DE (use spatial-de) and experiments without independent replicates.
trigger: condition comparison, pseudobulk, DESeq2, treatment vs control
tags:
- spatial
- condition
- pseudobulk
- differential-expression
---

# spatial-condition

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-condition")
adata = library.compare_conditions(read_input("data/samples.h5ad"))
write_output(library.results(adata), "tables/pseudobulk_de.csv")
```

## When to use

Compare conditions within each expression cluster using independent biological
samples. Both PyDESeq2 and Wilcoxon operate on sample-level pseudobulk counts.
Splitting spots from one sample does not create biological replicates.
For per-cluster marker genes use spatial-de.

## Inputs & Outputs

Input: AnnData with raw integer counts and sample/condition columns.
Counts are read from `layers["counts"]`, then `raw`, then `X`.
Nonfinite, negative or fractional counts are rejected, not rounded.
Missing default `leiden` labels trigger expression clustering; other missing
cluster columns raise.

Functions return the same AnnData plus accessible result tables and a figure.
CLI writes `processed.h5ad`, `report.md`, `result.json`,
`tables/pseudobulk_de.csv`, per-cluster and skipped-contrast tables,
and a diagnostic gallery. See [references/output_contract.md](references/output_contract.md)
for file names and generation conditions.

## Key CLI

```bash
python skills/spatial/spatial-condition/spatial_condition.py --input samples.h5ad --output results/condition --condition-key condition --sample-key sample_id --reference-condition control
python skills/spatial/spatial-condition/spatial_condition.py --demo --output /tmp/spatial_condition
```

`examples/example_step.py` checks sample-level counts on simulated data.
[references/parameters.md](references/parameters.md) lists all backend flags.

## Gotchas

- `tables/skipped_contrasts.csv` explains missing comparisons; absence is not
  evidence of no differential expression.
- `pseudobulk_de.csv` includes per-row method and sample counts. PyDESeq2 fit
  failures can use Wilcoxon; `run_info()["fallbacks"]` records the reason and
  requested/executed methods. Missing PyDESeq2 raises with an installer hint.
- `layers["counts"]` must be real counts, not rounded log-normalized expression.
- `condition_key` and `sample_key` must differ, and each sample must belong
  to exactly one condition.
- `n_samples_reference` and `n_samples_other` count samples, never spots.
  Two replicates per condition are the default minimum, not a power guarantee.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `compare_conditions(adata, *, condition_key: str='condition', sample_key: str='sample_id', cluster_key: str='leiden', method: str='pydeseq2', reference_condition: str | None=None, min_counts_per_gene: int=10, min_samples_per_condition: int=2, fdr_threshold: float=0.05, log2fc_threshold: float=1.0, random_state: int=0, **parameters)`

Aggregate counts per sample and cluster, then test conditions in place.

Both methods use biological-sample pseudobulk, not individual spots.
PyDESeq2 fitting failures may fall back to Wilcoxon, with warnings and a
per-contrast fallback record. Missing packages do not trigger fallback.

:param adata: AnnData with integer counts in layers['counts'], raw, or X,
    in that preference order; each sample belongs to exactly one condition.
:param condition_key: Condition column, default condition.
:param sample_key: Biological replicate column, default sample_id.
:param cluster_key: Cluster column, default leiden; missing leiden is computed.
:param method: pydeseq2 (default) or pseudobulk wilcoxon.
:param reference_condition: Reference label; None uses the first sorted condition.
:param min_counts_per_gene: Minimum total pseudobulk count, default 10.
:param min_samples_per_condition: Minimum independent replicates, default 2.
:param fdr_threshold: Adjusted p-value threshold, default 0.05.
:param log2fc_threshold: Absolute effect threshold for hit summaries, default 1.
:param random_state: Seed for clustering only if leiden is absent, default 0.
:param parameters: Backend options retain CLI defaults: pydeseq2_fit_type='parametric',
    pydeseq2_size_factors_fit_type='ratio', pydeseq2_refit_cooks=True,
    pydeseq2_alpha=0.05, pydeseq2_cooks_filter=True,
    pydeseq2_independent_filter=True, pydeseq2_n_cpus=1,
    wilcoxon_alternative='two-sided'.
:returns: The same AnnData with JSON-encoded tables and diagnostics; results
    returns the DE table and run_info includes skipped contrasts.
:raises ValueError: Invalid counts, design, cluster column or parameters.
:raises ImportError: Missing PyDESeq2; use install_skill_deps.

### `run_info(adata, *, keep: bool=True) -> dict`

Read comparison diagnostics and result tables.

:param adata: AnnData returned by compare_conditions.
:param keep: True retains diagnostics; False removes them for CLI serialization.
:returns: Summary including global_de, per_cluster_de and skipped contrasts.

### `results(adata) -> pd.DataFrame`

Return all tested genes across clusters and condition contrasts.

:param adata: Compared AnnData.
:returns: DataFrame with gene, log2fc, pvalue_adj, cluster, contrast and sample counts.
    Empty if every contrast was skipped or diagnostics were removed.

### `volcano_figure(adata, *, contrast: str | None=None)`

Plot log2 fold changes against adjusted p-values.

:param adata: Compared AnnData.
:param contrast: Optional exact contrast label; None shows all tested entries.
:returns: A matplotlib Figure; the caller saves and closes it.

<!-- api:end -->

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `pydeseq2`, `scanpy`, `scipy`, `seaborn`, `statsmodels`
