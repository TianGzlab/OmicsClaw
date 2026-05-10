<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--fdr-threshold`
- `--filter-compare-abs`
- `--filter-markers`
- `--group1`
- `--group2`
- `--groupby`
- `--log2fc-threshold`
- `--max-out-group-fraction`
- `--method`
- `--min-cells-per-sample`
- `--min-counts-per-gene`
- `--min-fold-change`
- `--min-in-group-fraction`
- `--n-top-genes`
- `--no-filter-compare-abs`
- `--no-filter-markers`
- `--no-pydeseq2-cooks-filter`
- `--no-pydeseq2-independent-filter`
- `--no-pydeseq2-refit-cooks`
- `--no-scanpy-pts`
- `--no-scanpy-rankby-abs`
- `--no-scanpy-tie-correct`
- `--pydeseq2-alpha`
- `--pydeseq2-cooks-filter`
- `--pydeseq2-fit-type`
- `--pydeseq2-independent-filter`
- `--pydeseq2-n-cpus`
- `--pydeseq2-refit-cooks`
- `--pydeseq2-size-factors-fit-type`
- `--sample-key`
- `--scanpy-corr-method`
- `--scanpy-pts`
- `--scanpy-rankby-abs`
- `--scanpy-tie-correct`

## Per-method parameter hints

### `pydeseq2`

**Tuning priority:** group1/group2 → sample_key → min_cells_per_sample/min_counts_per_gene → pydeseq2_fit_type/size_factors_fit_type → pydeseq2_alpha

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `leiden` |
| `group1` | `—` |
| `group2` | `—` |
| `sample_key` | `sample_id` |
| `n_top_genes` | `10` |
| `fdr_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |
| `min_cells_per_sample` | `10` |
| `min_counts_per_gene` | `10` |
| `pydeseq2_fit_type` | `parametric` |
| `pydeseq2_size_factors_fit_type` | `ratio` |
| `pydeseq2_refit_cooks` | `True` |
| `pydeseq2_alpha` | `0.05` |
| `pydeseq2_cooks_filter` | `True` |
| `pydeseq2_independent_filter` | `True` |
| `pydeseq2_n_cpus` | `1` |

**Requires:**
- `counts_or_raw`
- `obs.sample_key`
- `obs.groupby`

**Tips:**
- `pydeseq2` in `spatial-de` is intentionally restricted to explicit two-group contrasts with a real `sample_key`; OmicsClaw will not fabricate replicates.
- If the same biological samples contribute to both groups, OmicsClaw automatically uses a paired design (`~ sample_id + condition`).
- --min-cells-per-sample: wrapper-level gate for each sample x group pseudobulk profile before DESeq2 fitting.
- --min-counts-per-gene: wrapper-level pseudobulk gene filter applied before PyDESeq2.
- --pydeseq2-fit-type / --pydeseq2-size-factors-fit-type / --pydeseq2-refit-cooks / --pydeseq2-alpha / --pydeseq2-cooks-filter / --pydeseq2-independent-filter / --pydeseq2-n-cpus: official PyDESeq2 controls exposed directly by the wrapper.

### `t-test`

**Tuning priority:** groupby → scanpy_corr_method → filter_markers

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `leiden` |
| `group1` | `—` |
| `group2` | `—` |
| `n_top_genes` | `10` |
| `fdr_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |
| `scanpy_corr_method` | `benjamini-hochberg` |
| `scanpy_rankby_abs` | `False` |
| `scanpy_pts` | `False` |
| `filter_markers` | `True` |
| `min_in_group_fraction` | `0.25` |
| `min_fold_change` | `1.0` |
| `max_out_group_fraction` | `0.5` |
| `filter_compare_abs` | `False` |

**Requires:**
- `obs.groupby`
- `X_log_normalized`

**Tips:**
- --scanpy-corr-method / --scanpy-rankby-abs / --scanpy-pts: same official Scanpy controls as the Wilcoxon path.
- --filter-markers: keep this on for a first pass unless the user explicitly wants raw unfiltered ranking output.
- `t-test` is faster than Wilcoxon but remains an exploratory log-expression marker workflow rather than replicate-aware sample inference.

### `wilcoxon`

**Tuning priority:** groupby → scanpy_corr_method → filter_markers → scanpy_tie_correct

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `leiden` |
| `group1` | `—` |
| `group2` | `—` |
| `n_top_genes` | `10` |
| `fdr_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |
| `scanpy_corr_method` | `benjamini-hochberg` |
| `scanpy_rankby_abs` | `False` |
| `scanpy_pts` | `False` |
| `scanpy_tie_correct` | `False` |
| `filter_markers` | `True` |
| `min_in_group_fraction` | `0.25` |
| `min_fold_change` | `1.0` |
| `max_out_group_fraction` | `0.5` |
| `filter_compare_abs` | `False` |

**Requires:**
- `obs.groupby`
- `X_log_normalized`

**Tips:**
- --scanpy-corr-method: official `scanpy.tl.rank_genes_groups` multiple-testing correction (`benjamini-hochberg` or `bonferroni`).
- --scanpy-tie-correct: official Wilcoxon tie correction toggle in Scanpy; only relevant for `wilcoxon`.
- --scanpy-rankby-abs: ranks genes by absolute score but does not change the reported log fold-change sign.
- --scanpy-pts: asks Scanpy to report per-group detection fractions (`pct_nz_group`, `pct_nz_reference`).
- --filter-markers + min/max fraction controls: official `scanpy.tl.filter_rank_genes_groups` post-filter for cluster-style marker specificity.
