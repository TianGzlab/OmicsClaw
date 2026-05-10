<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--species`
- `--r-enhanced`

## Per-method parameter hints

### `qc_metrics`

**Tuning priority:** species

**Core parameters:**

| name | default |
|---|---|
| `species` | `human` |

**Requires:**
- `count_like_matrix_in_layers.raw_or_X`
- `gene_symbols_with_species_prefix_convention`

**Tips:**
- --species: Wrapper-level control for mitochondrial / ribosomal gene-prefix detection; use `human` for `MT-` / `RP[SL]`, `mouse` for `mt-` / `Rp[sl]`.
- Current OmicsClaw implementation exposes one public QC path, `qc_metrics`; it always computes ribosomal percentage in addition to mitochondrial percentage.
- This skill is diagnostic-only and does not remove cells or genes.
