<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--cluster-key`
- `--condition-key`
- `--fdr-threshold`
- `--log2fc-threshold`
- `--method`
- `--min-counts-per-gene`
- `--min-samples-per-condition`
- `--no-pydeseq2-cooks-filter`
- `--no-pydeseq2-independent-filter`
- `--no-pydeseq2-refit-cooks`
- `--pydeseq2-alpha`
- `--pydeseq2-cooks-filter`
- `--pydeseq2-fit-type`
- `--pydeseq2-independent-filter`
- `--pydeseq2-n-cpus`
- `--pydeseq2-refit-cooks`
- `--pydeseq2-size-factors-fit-type`
- `--reference-condition`
- `--sample-key`
- `--wilcoxon-alternative`

## Per-method parameter hints

### `pydeseq2`

**Tuning priority:** condition_key/sample_key/cluster_key → reference_condition → pydeseq2_fit_type/size_factors_fit_type → pydeseq2_alpha

**Core parameters:**

| name | default |
|---|---|
| `condition_key` | `condition` |
| `sample_key` | `sample_id` |
| `cluster_key` | `leiden` |
| `reference_condition` | `—` |
| `min_counts_per_gene` | `10` |
| `min_samples_per_condition` | `2` |
| `fdr_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |
| `pydeseq2_fit_type` | `parametric` |
| `pydeseq2_size_factors_fit_type` | `ratio` |
| `pydeseq2_alpha` | `0.05` |
| `pydeseq2_refit_cooks` | `True` |
| `pydeseq2_cooks_filter` | `True` |
| `pydeseq2_independent_filter` | `True` |
| `pydeseq2_n_cpus` | `1` |

**Requires:**
- `raw_or_counts`
- `obs.condition_key`
- `obs.sample_key`

**Tips:**
- --condition-key / --sample-key / --cluster-key: define the pseudobulk design before any statistical tuning.
- --reference-condition: determines the direction of the contrast and therefore the sign of log2FC.
- --min-counts-per-gene: OmicsClaw pseudobulk gene filter before DE testing.
- --min-samples-per-condition: wrapper-level replicate gate; use 2 as the minimum and prefer >=3.
- --pydeseq2-fit-type: official PyDESeq2 dispersion fit mode (`parametric` or `mean`).
- --pydeseq2-size-factors-fit-type: official PyDESeq2 size-factor strategy (`ratio`, `poscounts`, `iterative`).
- --pydeseq2-alpha: official DeseqStats significance target used during result filtering.
- --pydeseq2-refit-cooks / --pydeseq2-cooks-filter / --pydeseq2-independent-filter: official PyDESeq2 result-stabilizing controls.
- --pydeseq2-n-cpus: passed through to DeseqDataSet / DeseqStats.

### `wilcoxon`

**Tuning priority:** condition_key/sample_key/cluster_key → reference_condition → wilcoxon_alternative

**Core parameters:**

| name | default |
|---|---|
| `condition_key` | `condition` |
| `sample_key` | `sample_id` |
| `cluster_key` | `leiden` |
| `reference_condition` | `—` |
| `min_counts_per_gene` | `10` |
| `min_samples_per_condition` | `2` |
| `fdr_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |
| `wilcoxon_alternative` | `two-sided` |

**Requires:**
- `raw_or_counts`
- `obs.condition_key`
- `obs.sample_key`

**Tips:**
- --wilcoxon-alternative: official SciPy `ranksums` alternative hypothesis (`two-sided`, `less`, `greater`).
- --reference-condition: controls the comparison direction; OmicsClaw still reports log2FC relative to the reference.
- --min-samples-per-condition: keep this at >=2; Wilcoxon is a fallback, not a replacement for proper replicate-rich GLM analyses.
