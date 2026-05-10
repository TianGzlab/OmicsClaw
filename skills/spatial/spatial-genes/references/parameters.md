<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--flashs-bandwidth`
- `--flashs-n-rand-features`
- `--fdr-threshold`
- `--method`
- `--morans-coord-type`
- `--morans-corr-method`
- `--morans-n-neighs`
- `--morans-n-perms`
- `--n-top-genes`
- `--sparkx-max-genes`
- `--sparkx-num-cores`
- `--sparkx-option`
- `--spatialde-aeh-lengthscale`
- `--spatialde-aeh-patterns`
- `--spatialde-min-counts`
- `--spatialde-no-aeh`

## Per-method parameter hints

### `flashs`

**Tuning priority:** flashs_bandwidth → flashs_n_rand_features

**Core parameters:**

| name | default |
|---|---|
| `flashs_bandwidth` | `—` |
| `flashs_n_rand_features` | `500` |
| `fdr_threshold` | `0.05` |
| `n_top_genes` | `20` |

**Requires:**
- `obsm.spatial`
- `counts_or_raw`

**Tips:**
- --flashs-bandwidth: Wrapper-level override for the kernel bandwidth; default is estimated from coordinate spread.
- --flashs-n-rand-features: Wrapper-level sketch size controlling FlashS approximation fidelity vs runtime.

### `morans`

**Tuning priority:** morans_coord_type → morans_n_neighs → morans_n_perms

**Core parameters:**

| name | default |
|---|---|
| `morans_coord_type` | `auto` |
| `morans_n_neighs` | `6` |
| `morans_n_perms` | `100` |
| `morans_corr_method` | `fdr_bh` |
| `fdr_threshold` | `0.05` |
| `n_top_genes` | `20` |

**Requires:**
- `obsm.spatial`
- `X_log_normalized`

**Tips:**
- --morans-coord-type: `auto` lets Squidpy infer Visium grid vs generic coordinates.
- --morans-n-neighs: Main locality knob for generic coordinates.
- --morans-n-perms: Permutation depth; set 0 for analytic-only p-values.
- --morans-corr-method: Multiple-testing correction passed to Squidpy/statsmodels.

### `sparkx`

**Tuning priority:** sparkx_option → sparkx_num_cores → sparkx_max_genes

**Core parameters:**

| name | default |
|---|---|
| `sparkx_option` | `mixture` |
| `sparkx_num_cores` | `1` |
| `sparkx_max_genes` | `5000` |
| `fdr_threshold` | `0.05` |
| `n_top_genes` | `20` |

**Requires:**
- `obsm.spatial`
- `counts_or_raw`
- `Rscript`

**Tips:**
- --sparkx-option: Passed through to `spark.sparkx`; the official SPARK-X example uses `mixture`.
- --sparkx-num-cores: Passed through as `numCores` in the R implementation.
- --sparkx-max-genes: OmicsClaw wrapper cap for very large matrices before calling SPARK-X.

### `spatialde`

**Tuning priority:** spatialde_no_aeh → spatialde_min_counts → spatialde_aeh_patterns/aeh_lengthscale

**Core parameters:**

| name | default |
|---|---|
| `spatialde_no_aeh` | `False` |
| `spatialde_min_counts` | `3` |
| `spatialde_aeh_patterns` | `—` |
| `spatialde_aeh_lengthscale` | `—` |
| `fdr_threshold` | `0.05` |
| `n_top_genes` | `20` |

**Requires:**
- `obsm.spatial`
- `counts_or_raw`

**Tips:**
- --spatialde-min-counts: Gene prefilter before Gaussian-process fitting.
- --spatialde-no-aeh: Skip the AEH pattern-grouping stage and only return per-gene SpatialDE statistics.
- --spatialde-aeh-patterns / --spatialde-aeh-lengthscale: Optional overrides for AEH pattern count `C` and lengthscale `l`.
