<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--batch-key`
- `--cell-type-key`
- `--cellassign-max-epochs`
- `--cluster-key`
- `--layer`
- `--marker-n-genes`
- `--marker-overlap-method`
- `--marker-overlap-normalize`
- `--marker-padj-cutoff`
- `--marker-rank-method`
- `--method`
- `--model`
- `--reference`
- `--scanvi-max-epochs`
- `--scanvi-n-hidden`
- `--scanvi-n-layers`
- `--scanvi-n-latent`
- `--species`
- `--tangram-device`
- `--tangram-num-epochs`
- `--tangram-train-genes`

## Per-method parameter hints

### `cellassign`

**Tuning priority:** model/species → layer → batch_key → cellassign_max_epochs

**Core parameters:**

| name | default |
|---|---|
| `model` | `—` |
| `species` | `human` |
| `layer` | `counts` |
| `batch_key` | `—` |
| `cellassign_max_epochs` | `400` |

**Requires:**
- `counts_or_raw`

**Tips:**
- --model: OmicsClaw wrapper path to a JSON marker-panel file; if omitted, built-in species signatures are used.
- --layer / --batch-key: Passed to `CellAssign.setup_anndata(..., layer=..., batch_key=...)`.
- --cellassign-max-epochs: Passed to `model.train(max_epochs=...)`.

### `marker_based`

**Tuning priority:** cluster_key → marker_rank_method → marker_n_genes / marker_padj_cutoff

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `species` | `human` |
| `marker_rank_method` | `wilcoxon` |
| `marker_n_genes` | `50` |
| `marker_overlap_method` | `overlap_count` |
| `marker_overlap_normalize` | `reference` |
| `marker_padj_cutoff` | `—` |

**Requires:**
- `X_log_normalized`
- `cluster_labels`

**Tips:**
- --marker-rank-method: Passed to `scanpy.tl.rank_genes_groups`; OmicsClaw defaults to `wilcoxon`.
- --marker-n-genes: Passed through as `top_n_markers` for `scanpy.tl.marker_gene_overlap`; set `0` to switch to adjusted-p-value marker selection.
- --marker-overlap-method / --marker-overlap-normalize: Passed to `scanpy.tl.marker_gene_overlap`; `reference` normalization preserves the old overlap / signature-size behavior.
- --marker-padj-cutoff: Only takes effect when `--marker-n-genes 0`, matching Scanpy's documented precedence.

### `scanvi`

**Tuning priority:** reference → cell_type_key → batch_key/layer → scanvi_n_latent

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `batch_key` | `—` |
| `layer` | `counts` |
| `scanvi_n_hidden` | `128` |
| `scanvi_n_latent` | `10` |
| `scanvi_n_layers` | `1` |
| `scanvi_max_epochs` | `100` |

**Requires:**
- `reference_h5ad`
- `counts_or_raw`

**Tips:**
- --layer / --batch-key: Passed to `SCVI.setup_anndata` / `SCANVI.setup_anndata`; use them when raw counts live outside `layers['counts']` or batch structure matters.
- --scanvi-n-hidden / --scanvi-n-latent / --scanvi-n-layers: Passed to the underlying `scvi.model.SCVI(...)` encoder-decoder.
- --scanvi-max-epochs: Current OmicsClaw wrapper uses this for SCVI pretraining, SCANVI finetuning, and query adaptation.

### `tangram`

**Tuning priority:** reference → cell_type_key → tangram_num_epochs → tangram_train_genes

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `tangram_num_epochs` | `500` |
| `tangram_device` | `auto` |
| `tangram_train_genes` | `2000` |

**Requires:**
- `reference_h5ad`
- `X_log_normalized`

**Tips:**
- --tangram-num-epochs: Passed to `tg.map_cells_to_space(..., num_epochs=...)`.
- --tangram-device: Passed to `tg.map_cells_to_space(..., device=...)`; `auto` resolves to CUDA, MPS, or CPU in that order.
- --tangram-train-genes: OmicsClaw wrapper control for the gene list passed into `tg.pp_adatas(..., genes=...)`; `0` means all shared genes.
