<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--data-type`
- `--leiden-resolution`
- `--max-genes`
- `--max-mt-pct`
- `--min-cells`
- `--min-genes`
- `--n-neighbors`
- `--n-pcs`
- `--n-top-hvg`
- `--resolutions`
- `--species`
- `--tissue`

## Per-method parameter hints

### `scanpy_standard`

**Tuning priority:** tissue → min_genes/max_mt_pct/max_genes → n_top_hvg → n_pcs/n_neighbors → leiden_resolution

**Core parameters:**

| name | default |
|---|---|
| `data_type` | `generic` |
| `species` | `human` |
| `tissue` | `—` |
| `min_genes` | `0` |
| `min_cells` | `0` |
| `max_mt_pct` | `20.0` |
| `max_genes` | `0` |
| `n_top_hvg` | `2000` |
| `n_pcs` | `30` |
| `n_neighbors` | `15` |
| `leiden_resolution` | `0.5` |
| `resolutions` | `—` |

**Requires:**
- `raw_counts_in_X`
- `obsm.spatial_optional`
- `scanpy_pipeline`

**Tips:**
- --tissue: OmicsClaw wrapper-level preset that fills QC defaults; reports also record the effective thresholds after preset resolution.
- --min-genes / --max-mt-pct / --max-genes: main QC thresholds controlling how aggressively low-quality spots are removed.
- --n-top-hvg: public Scanpy HVG selection budget passed to `pp.highly_variable_genes(..., flavor='seurat_v3', layer='counts')`.
- --n-pcs / --n-neighbors: public Scanpy graph-construction controls; OmicsClaw reports requested, computed, used, and suggested PCs separately.
- --leiden-resolution / --resolutions: public Leiden clustering resolution controls for the primary clustering and optional sweep.
