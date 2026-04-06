---
doc_id: skill-guide-spatial-preprocess
title: OmicsClaw Skill Guide — Spatial Preprocess
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-preprocessing, spatial-preprocess, preprocess]
search_terms: [spatial preprocess, spatial preprocessing, QC, visium, xenium, leiden, umap, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Preprocess

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-preprocess` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for preprocessing parameter
reasoning, loader expectations, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:
- how to explain the current `scanpy_standard` preprocessing workflow
- which QC and graph parameters matter first for a spatial dataset
- how to distinguish wrapper-level loader controls from actual preprocessing controls

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:
- **Input type**:
  - `raw_counts.h5ad` emitted by `spatial-raw-processing`
  - Visium directory or feature matrix
  - Xenium `.zarr` / `.h5ad`
  - converted `.h5ad` for MERFISH / Slide-seq / seqFISH
  - if the user still has FASTQ pairs plus IDs / STAR reference files, route to `spatial-raw-processing` instead
- **Matrix representation**:
  - current wrapper expects raw counts in `X` on input
  - if the input already looks log-normalized or scaled, say that explicitly before preprocessing
- **Spatial coordinates**:
  - coordinates are strongly preferred
  - preprocessing can still run without them, but downstream spatial plots and analyses will be limited
- **Species**:
  - current wrapper only exposes `human` and `mouse`
  - this matters for mitochondrial prefix detection (`MT-` vs `mt-`)
- **Dataset size and sparsity**:
  - very sparse datasets interact strongly with `min_genes`, `max_mt_pct`, and `n_top_hvg`
- **Biological context**:
  - if the tissue is obvious, a tissue preset may be a reasonable first-pass shortcut

Important implementation notes in current OmicsClaw:
- The current skill exposes one implemented workflow: `scanpy_standard`.
- `data_type`, `species`, and `tissue` are wrapper-level controls, not alternative preprocessing algorithms.
- Tissue presets only fill thresholds when the user has not already supplied explicit values.
- Reports now record the **effective** thresholds after preset application.
- Raw counts are preserved in both `adata.layers["counts"]` and `adata.raw`.
- PCA is computed on the HVG subset, and the neighbor graph uses a clipped PC count that may be lower than the requested count if the data shape requires it.

## Step 2: Explain The Current Workflow Correctly

Current OmicsClaw `spatial-preprocess` runs:
1. QC metric calculation with mitochondrial annotation.
2. Spot / gene filtering.
3. Raw-count preservation.
4. Library-size normalization and `log1p`.
5. `seurat_v3` highly variable gene selection on the counts layer.
6. Scaling, PCA, neighbors, UMAP, and Leiden clustering.

Do **not** describe this as if the user were choosing among multiple
implemented preprocessing backends. Right now, the choice is mainly about
thresholds, graph construction, and loader hints.

## Step 3: Pick Parameters Deliberately

Use this quick guide when the user has not specified exact thresholds:

| Parameter group | Best first use | Strong starting point | Main caveat |
|-----------------|----------------|-----------------------|-------------|
| **Tissue preset** | Fast first pass when tissue identity is obvious | `tissue=brain`, `tissue=tumor`, etc. | Presets are wrapper-level shortcuts, not universal truth |
| **QC thresholds** | Core quality filtering | start with preset or `min_genes=200`, `max_mt_pct=10~20` depending on tissue | Over-filtering can remove biologically real regions |
| **HVG budget** | Feature selection for PCA / graph | `n_top_hvg=2000` | Too low can oversimplify; too high can add noise |
| **Graph size** | neighborhood structure | `n_pcs=30`, `n_neighbors=15` | Optimal values depend on dataset size and heterogeneity |
| **Leiden resolution** | cluster granularity | `leiden_resolution=0.5` | Higher resolution is not automatically better |
| **Resolution sweep** | exploratory clustering | `resolutions=0.4,0.6,0.8,1.0` | Useful for exploration, not always needed in the first pass |

## Step 4: Always Show An Effective Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial preprocessing
  Workflow: scanpy_standard
  Loader: data_type=visium
  Effective QC: min_genes=200, min_cells=0, max_mt_pct=10, max_genes=6000
  Graph: n_top_hvg=2000, n_pcs=30, n_neighbors=15, leiden_resolution=0.5
  Note: brain preset was used to fill QC defaults, but these effective thresholds are what will actually be applied.
```

This is important because saying only "I will use the brain preset" is not
precise enough for reproducibility.

## Step 5: Parameter-Specific Tuning Rules

### Tissue preset

Tune in this order:
1. `tissue`
2. explicit threshold overrides

Guidance:
- Use a tissue preset only when the tissue identity is reasonably clear.
- If the user already knows the right QC regime, explicit numeric thresholds are better than relying entirely on a preset.
- If a preset is used, explain the resolved values before execution.

Important warning:
- Tissue presets are OmicsClaw wrapper knowledge, not upstream Scanpy APIs.

### QC thresholds

Tune in this order:
1. `min_genes`
2. `max_mt_pct`
3. `max_genes`
4. `min_cells`

Guidance:
- Raise `min_genes` when extremely sparse spots are dominating the dataset.
- Lower `min_genes` when sparse biology is expected and the user accepts more noise.
- Lower `max_mt_pct` when mitochondrial-rich low-quality spots are obvious.
- Raise `max_mt_pct` cautiously in tissues like heart or muscle where higher mitochondrial load may be biological.
- Use `max_genes` as an upper-bound guard when obvious doublet-like or overly complex spots are a concern.
- Use `min_cells` when you want to remove genes detected in very few spots before downstream modeling.

Important warning:
- Aggressive QC may remove real tissue niches, especially in sparse or damaged specimens.

### HVG budget

Tune in this order:
1. `n_top_hvg`

Guidance:
- Start with `n_top_hvg=2000`.
- Increase it when the dataset is large and biologically diverse.
- Reduce it when the dataset is small or noisy and the user wants a tighter feature set.

Important warning:
- In current OmicsClaw, HVG selection uses `flavor="seurat_v3"` on the counts layer, not on log-normalized `adata.X`.

### PCA and graph construction

Tune in this order:
1. `n_pcs`
2. `n_neighbors`

Guidance:
- Start with `n_pcs=30` and `n_neighbors=15`.
- Larger `n_pcs` can help when the dataset is complex, but the wrapper may clip the effective number based on matrix shape.
- Lower `n_neighbors` when you want more local structure.
- Raise `n_neighbors` when you want smoother, broader neighborhoods.
- After the run, compare requested PCs to computed / used / suggested PCs instead of assuming they were identical.

Important warning:
- Requested PCs and effective PCs are not always the same in the current wrapper.

### Leiden resolution

Tune in this order:
1. `leiden_resolution`
2. `resolutions`

Guidance:
- Start with `leiden_resolution=0.5`.
- Increase it when the current clustering is too coarse.
- Lower it when clusters are obviously over-split.
- Use `resolutions` when the user explicitly wants exploratory granularity comparisons.

Important warning:
- A larger number of clusters is not automatically a better preprocessing result.

## Step 6: What To Say After The Run

- If very few spots remain after QC: mention that thresholds were likely too strict and point to `min_genes`, `max_mt_pct`, or `max_genes`.
- If no spatial coordinates are present: explain that preprocessing succeeded, but spatial plots and downstream spatial analyses may be limited.
- If clustering is too coarse: suggest revisiting `leiden_resolution` or `n_neighbors`.
- If clustering is too fragmented: suggest lowering `leiden_resolution` or increasing `n_neighbors`.
- If requested PCs were much larger than used PCs: explain that the wrapper clipped the effective dimensionality based on the available HVGs and cells.
- If the dataset appears already normalized on input: mention that the preprocessing assumptions may be violated and the user should confirm whether rerunning normalization is appropriate.

## Step 7: Explain Outputs Correctly

When summarizing results:
- describe `processed.h5ad` as the downstream-ready AnnData
- describe `tables/qc_summary.csv` as the compact summary of retained size and PCA usage
- describe `tables/cluster_summary.csv` as the primary Leiden cluster sizes
- describe `tables/multi_resolution_summary.csv` as optional exploratory output when a resolution sweep was run
- describe `effective_params` in `result.json` and `report.md` as the actual thresholds and graph settings that governed the preprocessing run

Do **not** say "the preset was brain, so preprocessing is reproducible" without
also stating the resolved thresholds. In current OmicsClaw, the effective
values are what matter for interpretation and reruns.
