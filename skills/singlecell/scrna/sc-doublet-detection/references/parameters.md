<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--batch-key`
- `--doubletdetection-n-iters`
- `--doubletdetection-standard-scaling`
- `--expected-doublet-rate`
- `--method`
- `--r-enhanced`
- `--random-state`
- `--scds-mode`
- `--threshold`

## Per-method parameter hints

### `doubletdetection`

**Tuning priority:** doubletdetection_n_iters

**Core parameters:**

| name | default |
|---|---|
| `doubletdetection_n_iters` | `10` |
| `doubletdetection_standard_scaling` | `False` |

**Requires:**
- `doubletdetection`
- `raw_count_like_input`

**Tips:**
- --method doubletdetection: consensus Python path borrowed from SCOP's method surface.
- The current wrapper records expected_doublet_rate for context, but the native DoubletDetection classifier does not use it directly.

### `doubletfinder`

**Tuning priority:** expected_doublet_rate

**Core parameters:**

| name | default |
|---|---|
| `expected_doublet_rate` | `0.06` |

**Requires:**
- `R_doubletfinder_stack`

**Tips:**
- --method doubletfinder: R-backed Seurat path.
- If the R runtime fails, the wrapper falls back to scDblFinder and reports both methods.

### `scdblfinder`

**Tuning priority:** expected_doublet_rate

**Core parameters:**

| name | default |
|---|---|
| `expected_doublet_rate` | `0.06` |

**Requires:**
- `R_scdblfinder_stack`

**Tips:**
- --method scdblfinder: fast Bioconductor path with a compact wrapper surface.

### `scds`

**Tuning priority:** expected_doublet_rate -> scds_mode

**Core parameters:**

| name | default |
|---|---|
| `expected_doublet_rate` | `0.06` |
| `scds_mode` | `cxds` |

**Requires:**
- `R_scds_stack`

**Tips:**
- --method scds: Bioconductor score family from SCOP.
- --scds-mode chooses which score (`hybrid`, `cxds`, or `bcds`) becomes the public call surface.
- In the current environment, `cxds` is the safest first-pass default.

### `scrublet`

**Tuning priority:** expected_doublet_rate -> batch_key

**Core parameters:**

| name | default |
|---|---|
| `expected_doublet_rate` | `0.06` |
| `batch_key` | `—` |

**Advanced parameters:**

| name | default |
|---|---|
| `threshold` | `auto` |

**Requires:**
- `scrublet`
- `raw_count_like_input`

**Tips:**
- --method scrublet: default Python-native path.
- --batch-key: useful when captures/samples are mixed and Scrublet should run per batch.
- --threshold: manual cutoff overriding Scrublet's automatic call.
