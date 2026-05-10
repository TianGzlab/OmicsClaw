<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--allow-simplified-grn`
- `--cluster-key`
- `--db`
- `--motif`
- `--n-jobs`
- `--n-top-targets`
- `--seed`
- `--tf-list`
- `--r-enhanced`

## Per-method parameter hints

### `pyscenic_workflow`

**Tuning priority:** tf_list -> db -> motif -> n_top_targets -> n_jobs

**Core parameters:**

| name | default |
|---|---|
| `tf_list` | `—` |
| `db` | `—` |
| `motif` | `—` |
| `n_top_targets` | `50` |
| `n_jobs` | `4` |
| `seed` | `42` |

**Requires:**
- `preprocessed_anndata`
- `pyscenic`
- `arboreto`
- `TF_list`
- `cisTarget_database`
- `motif_annotations`

**Tips:**
- --tf-list, --db, and --motif are the core external resources for a full pySCENIC run.
- --n-top-targets: Wrapper-level export cap for the top targets retained per regulon.
