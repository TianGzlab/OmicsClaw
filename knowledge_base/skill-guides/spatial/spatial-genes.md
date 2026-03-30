---
doc_id: skill-guide-spatial-genes
title: OmicsClaw Skill Guide — Spatially Variable Genes
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-genes, spatial-svg-detection, genes]
search_terms: [spatially variable genes, SVG, Moran, SpatialDE, SPARK-X, FlashS, tuning, counts layer]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatially Variable Genes

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-genes` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:
- which SVG method is the best first pass for a given dataset
- which parameters matter first in the current OmicsClaw wrapper
- how to explain score semantics and data requirements correctly

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:
- **Spot / cell count**:
  - `<= 5k`: small
  - `5k - 30k`: medium
  - `> 30k`: large
- **Spatial coordinates**: `obsm["spatial"]` or equivalent must exist for all methods.
- **Expression representation**:
  - `adata.X` should contain log-normalized expression for `morans`.
  - `layers["counts"]` or `adata.raw` is strongly preferred for `spatialde`, `sparkx`, and `flashs`.
- **Platform / coordinate layout**:
  - Visium-like grid data may benefit from `morans_coord_type=grid` or `auto`.
  - Irregular coordinates usually need `morans_coord_type=generic` or `auto`.
- **Gene-space size**:
  - Very large gene sets affect `sparkx_max_genes` and runtime.
  - Very sparse genes interact strongly with `spatialde_min_counts`.

Important implementation notes in current OmicsClaw:
- `morans` runs on `adata.X` and uses Squidpy neighbor graph construction.
- `spatialde`, `sparkx`, and `flashs` prefer raw counts in `layers["counts"]`; if unavailable, the wrapper falls back to `adata.raw` or `adata.X` with a warning.
- `SPARK-X` requires `Rscript` plus the R `SPARK` package.
- `FlashS` currently exposes `--flashs-bandwidth` and `--flashs-n-rand-features` as **OmicsClaw wrapper-level controls**; do not describe them as guaranteed upstream public API flags.
- If `--spatialde-no-aeh` is set, OmicsClaw intentionally skips AEH pattern grouping even if AEH-specific arguments were supplied.
- The standard Python result layer is now a recipe-driven gallery under `figures/`, and downstream visualization contracts are exported under `figure_data/`.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **Moran's I** | Best default baseline for most preprocessed datasets | `morans_coord_type=auto`, `morans_n_neighs=6`, `morans_n_perms=100`, `morans_corr_method=fdr_bh` | Sensitive to neighborhood construction; wrong grid/generic assumption can distort results |
| **SpatialDE** | Smooth gradients / broad spatial trends, especially when pattern grouping matters | `spatialde_min_counts=3~10`, AEH on by default, `spatialde_no_aeh=true` for a quick ranking-only first pass | Slower than Moran; AEH is only useful if enough significant genes exist |
| **SPARK-X** | Medium-to-large count-based datasets when R is available | `sparkx_option=mixture`, `sparkx_num_cores=1~4`, `sparkx_max_genes=3000~5000` | Depends on R/SPARK and may need gene capping for runtime |
| **FlashS** | Very large datasets or a fast first screening pass | `flashs_n_rand_features=500`, data-adaptive `flashs_bandwidth` | Approximate wrapper score; not the same statistical semantics as Moran or SpatialDE |

Practical default decision order:
1. If the user just says "find spatially variable genes" and gives no method, start with **Moran's I** for small/medium datasets.
2. If the dataset is large or the user wants a fast first pass, consider **FlashS** first.
3. Use **SPARK-X** when the user wants a count-based method on a medium/large dataset and R dependencies are available.
4. Use **SpatialDE** when the user explicitly wants smooth spatial gradients or AEH-style pattern grouping.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatially variable gene detection
  Method: Moran's I
  Parameters: morans_coord_type=auto, morans_n_neighs=6, morans_n_perms=100, morans_corr_method=fdr_bh
  Dataset size: 12,842 spots × 4,000 genes
  Note: This is a medium-sized dataset, so Moran's I is a strong first pass before heavier count-based methods.
```

## Step 4: Method-Specific Tuning Rules

### Moran's I

Tune in this order:
1. `morans_coord_type`
2. `morans_n_neighs`
3. `morans_n_perms`
4. `morans_corr_method`

Guidance:
- Start with `morans_coord_type=auto`.
- Use `generic` when coordinates are irregular and clearly not array-grid-like.
- Use `grid` only when the platform geometry is truly grid-like.
- Start with `morans_n_neighs=6`; raise it for broader neighborhoods and smoother domains, lower it for finer local patterns.
- `morans_n_perms=0` is acceptable for a quick analytic-only pass, but `100~500` is more defensible when permutation support is desired.
- Keep `morans_corr_method=fdr_bh` unless the user explicitly needs a different multiple-testing correction.

Important warnings:
- Do not assume Moran's score is comparable to SPARK-X or SpatialDE scores.
- If top genes change sharply between `auto`, `grid`, and `generic`, the coordinate model choice is part of the result and should be discussed explicitly.

### SpatialDE

Tune in this order:
1. `spatialde_min_counts`
2. `spatialde_no_aeh`
3. `spatialde_aeh_patterns`
4. `spatialde_aeh_lengthscale`

Guidance:
- Start with `spatialde_min_counts=3`.
- Raise `spatialde_min_counts` toward `5~10` when many extremely sparse genes are dominating runtime or noise.
- For a quick ranking-only first pass, use `spatialde_no_aeh=true`.
- Only tune `spatialde_aeh_patterns` and `spatialde_aeh_lengthscale` when the user actually wants pattern grouping and there are enough significant genes to support it.
- If the user mainly wants a ranked SVG table, do not force AEH.

Important warnings:
- AEH may be skipped when too few significant genes are available; this is expected behavior, not necessarily a failure.
- Do not describe SpatialDE output as Moran's I. Its main ranking score is `LLR`, and significance should be interpreted through `qval`.

### SPARK-X

Tune in this order:
1. `sparkx_option`
2. `sparkx_num_cores`
3. `sparkx_max_genes`

Guidance:
- Start with `sparkx_option=mixture`; this matches the official example and is the safest default.
- Increase `sparkx_num_cores` when the environment has available CPU and the dataset is large.
- Use `sparkx_max_genes=3000~5000` for a scalable first pass on large matrices.
- Set `sparkx_max_genes=0` only when the user explicitly wants a full-gene run and accepts the runtime cost.

Important warnings:
- Do not treat `sparkx_max_genes` as a scientific parameter of SPARK-X itself; it is an OmicsClaw wrapper-level scalability control.
- OmicsClaw reports SPARK-X ranking as `-log10(p)` for readability, but significance should be interpreted using `qval` when available.

### FlashS

Tune in this order:
1. `flashs_bandwidth`
2. `flashs_n_rand_features`

Guidance:
- Leave `flashs_bandwidth` unset at first to use the wrapper's data-adaptive estimate.
- Increase `flashs_bandwidth` when the user cares about broad tissue-scale trends.
- Decrease `flashs_bandwidth` when the user wants finer local microenvironment patterns.
- Start with `flashs_n_rand_features=500`.
- Raise `flashs_n_rand_features` toward `1000+` when a larger dataset or a finer approximation is needed and runtime is acceptable.

Important warnings:
- `flashs_bandwidth` and `flashs_n_rand_features` are wrapper-level approximation controls, not universal upstream method parameters.
- Do not describe the FlashS score as a p-value. OmicsClaw reports a wrapper score plus BH-adjusted `qval`.

## Step 5: Large-Dataset Rules

For `>30k` spots / cells:
- Prefer **FlashS** or **SPARK-X** as the first run.
- Moran's I is still acceptable as a baseline, but explain that neighborhood construction and runtime may become more sensitive.
- Avoid starting with **SpatialDE** unless the user explicitly wants Gaussian-process modeling or AEH patterns.

For very uncertain spatial scale:
- Start with **Moran's I** or **FlashS** as a first pass.
- If the first run mostly finds broad gradients, widen the neighborhood scale or bandwidth.
- If the first run misses fine local structure, shrink the neighborhood scale or bandwidth.

## Step 6: What To Say After The Run

- If `n_significant == 0` or is extremely low: mention possible causes including missing raw counts for count-based methods, overly strict `fdr_threshold`, overly high `spatialde_min_counts`, or a mismatched Moran neighborhood definition.
- If an unusually large fraction of genes is significant: mention possible over-smoothing, depth-driven gradients, or technical artifacts; suggest reviewing preprocessing and neighborhood scale.
- If top genes are dominated by mitochondrial, ribosomal, or obvious QC-related features: flag a likely preprocessing / normalization issue before over-interpreting biology.
- If Moran's I results look spatially fragmented: suggest revisiting `morans_coord_type` and `morans_n_neighs`.
- If SpatialDE skips AEH: explain that fewer than 5 significant genes were available for stable pattern grouping.
- If SPARK-X is too slow: suggest increasing `sparkx_num_cores` or lowering `sparkx_max_genes` for the next pass.
- If FlashS results are too coarse: suggest lowering `flashs_bandwidth`.
- If FlashS misses broad tissue gradients: suggest increasing `flashs_bandwidth`.
- If two methods disagree strongly: explain that they target different spatial assumptions and scales; compare overlap and biological plausibility rather than assuming one method is wrong.

## Step 6.5: Explain The Visualization Contract Correctly

After a successful run, describe outputs in two layers:

- **Python standard gallery**: this is the canonical OmicsClaw result layer. It should be the first thing users inspect.
- **R customization layer**: this is optional and should consume `figure_data/` exports rather than recomputing SVG statistics.

Current `spatial-genes` gallery roles are:
- `overview`: top SVG spatial and UMAP maps
- `diagnostic`: score-vs-significance and Moran ranking when available
- `supporting`: top SVG score summary
- `uncertainty`: significance distribution across tested genes

If the user asks for prettier or journal-style figures, point them to:
- `figure_data/top_svg_spatial_points.csv`
- `figure_data/top_svg_umap_points.csv`
- `figure_data/top_svg_scores.csv`
- `reproducibility/r_visualization.sh`

## Step 7: Explain Results Using Method-Correct Language

When summarizing results to the user:
- For **Moran's I**, refer to the score as `Moran's I`.
- For **SpatialDE**, refer to the score as `LLR` and significance as `q-value`.
- For **SPARK-X**, refer to the displayed ranking score as `-log10(p)` and significance as `q-value` when present.
- For **FlashS**, refer to the displayed ranking score as `FlashS score` and significance as `q-value`.

Do **not** collapse all methods into a generic "p-value ranking" explanation.
The ranking score and significance column are method-specific in current
OmicsClaw outputs.
