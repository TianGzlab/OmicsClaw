---
doc_id: skill-guide-spatial-domains
title: OmicsClaw Skill Guide — Spatial Domains
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-domains, spatial-domain-identification, domains]
search_terms: [spatial domains, leiden, louvain, CellCharter, BANKSY, SpaGCN, STAGATE, GraphST, tuning, clustering]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Domains

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-domains` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:
- which spatial domain method is the best first pass for a given dataset
- which parameters matter first for OmicsClaw's current wrapper
- how to explain tradeoffs without over-claiming that every setting is equally validated

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:
- **Spot / cell count**:
  - `<= 5k`: small
  - `5k - 30k`: medium
  - `> 30k`: large
- **Spatial coordinates**: `obsm["spatial"]` or equivalent must exist for all methods.
- **Embedding availability**: `obsm["X_pca"]` is strongly preferred for Leiden, Louvain, and CellCharter.
- **Raw counts availability**: `layers["counts"]` or `adata.raw` is especially important for GraphST and BANKSY.
- **Platform / coordinate scale**: Visium, Slide-seqV2, Stereo-seq, Xenium-like data affect `rad_cutoff`, runtime, and neighborhood choices.

Important implementation notes in current OmicsClaw:
- If `X_pca` is missing, the CLI wrapper will auto-compute PCA before running.
- For `spagcn`, `stagate`, and `graphst`, if `--n-domains` is omitted, OmicsClaw defaults it to `7`.
- `SpaGCN` in the current wrapper runs with `histology=False`; do not promise H&E-aware segmentation in this workflow.
- The standard Python result layer is now a recipe-driven gallery under `figures/`, and downstream visualization contracts are exported under `figure_data/`.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **Leiden** | Fast baseline for almost all datasets | `resolution=0.8~1.2`, `spatial_weight=0.2~0.4` | Can under-use spatial context if `spatial_weight` is too low |
| **Louvain** | Legacy / parity with older workflows | `resolution=0.8~1.2`, `spatial_weight=0.2~0.4` | Usually choose Leiden unless user specifically wants Louvain |
| **CellCharter** | Strong general-purpose spatial domains, especially when K is unknown | `auto_k=true`, `auto_k_min=2`, `auto_k_max=8~12`, `n_layers=3`, `use_rep=X_pca` | Higher `n_layers` increases memory and broadens neighborhoods |
| **BANKSY** | Explicit control over fine niches vs broad domains | `lambda_param=0.2` for niches, `0.8` for broad domains | `lambda_param` strongly changes the biological meaning of clusters |
| **SpaGCN** | Spatially smooth domains when user explicitly wants a GNN-style method | `n_domains=7`, `spagcn_p=0.5`, `epochs=100~200` | Slower on large data; current wrapper is coordinate-based, not histology-aware |
| **STAGATE** | Deep spatial autoencoder with adaptive KNN graph | `n_domains=7`, `k_nn=6`, `epochs=100~200` | Radius mode is fragile if coordinate scales are inconsistent |
| **GraphST** | Self-supervised deep model when raw counts are available | `n_domains=7`, `epochs=50~100` on large data, `dim_output=64` | Can be slow and produce speckled labels on large tissues |

Practical default decision order:
1. If the user only says "find spatial domains" and gives no method, start with **Leiden** or **CellCharter**.
2. If the user wants broader spatial structure with explicit neighborhood mixing, consider **BANKSY**.
3. Use **SpaGCN / STAGATE / GraphST** when the user explicitly asks for deep / graph neural methods, or when the baseline methods are not satisfactory.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial domain identification
  Method: CellCharter
  Parameters: auto_k=true, auto_k_min=2, auto_k_max=10, n_layers=3, use_rep=X_pca
  Dataset size: 41,786 spots
  Note: This is a large dataset, so CellCharter is a safer first pass than GraphST/SpaGCN.
```

## Step 4: Method-Specific Tuning Rules

### Leiden

Tune in this order:
1. `resolution`
2. `spatial_weight`

Guidance:
- Start around `resolution=0.8~1.0`.
- Increase `resolution` when too few domains are found.
- Decrease `resolution` when domains are overly fragmented.
- Increase `spatial_weight` when labels are spatially fragmented and expression-only clustering is dominating.

### Louvain

Tune in this order:
1. `resolution`
2. `spatial_weight`

Guidance:
- Use the same general tuning logic as Leiden.
- Prefer Leiden as the default unless Louvain is specifically required.

### CellCharter

Tune in this order:
1. `auto_k` or fixed `n_domains`
2. `n_layers`
3. `use_rep`

Guidance:
- If the user does not know K, start with `auto_k=true`.
- A good default search range is `auto_k_min=2`, `auto_k_max=8~12`.
- Use fixed `n_domains` only when the expected domain count is already motivated.
- Start with `n_layers=3`; use `2` for more local structure, `4+` for broader tissue context.
- Prefer `use_rep=X_pca` unless a better embedding already exists.

Important warning:
- If auto-K picks the minimum or maximum tested K, the search range may be too narrow. Shift or widen the range before over-interpreting the result.

### BANKSY

Tune in this order:
1. `lambda_param`
2. `num_neighbours`
3. `resolution` or `n_domains`

Guidance:
- `lambda_param=0.2` favors fine-grained cell typing / niches.
- `lambda_param=0.8` favors broad domain finding.
- Start with `num_neighbours=15`.
- If the user wants an exact number of domains, specify `n_domains`.
- If the user wants exploratory clustering, use `resolution`.

Important warning:
- `lambda_param` changes the biological interpretation substantially. Do not treat `0.2` and `0.8` runs as equivalent.

### SpaGCN

Tune in this order:
1. `spagcn_p`
2. `n_domains`
3. `epochs`

Guidance:
- Start with `spagcn_p=0.5`.
- Lower toward `0.3` if expression should dominate more.
- Raise toward `0.7` if stronger spatial coherence is desired.
- Start with `epochs=100`; move toward `200` when convergence appears weak.

Important warnings:
- OmicsClaw will default `n_domains` to `7` if omitted, but this should still be explained to the user.
- Current OmicsClaw SpaGCN flow does **not** use histology images; do not describe the run as image-aware.
- On large datasets, SpaGCN can be slow; do not choose it blindly as the first pass.

### STAGATE

Tune in this order:
1. `k_nn` or `rad_cutoff`
2. `stagate_alpha` and `pre_resolution`
3. `epochs`

Guidance:
- Prefer `k_nn=6` as the default because it is less sensitive to coordinate scaling.
- Use `rad_cutoff` only when the platform scale is known and stable.
- `stagate_alpha=0` is the default safe baseline.
- Increase `stagate_alpha` only when explicitly using the cell-type-aware extension.
- Start with `epochs=100`; increase toward `200` if needed.

Important warning:
- Do not recommend `rad_cutoff` casually across platforms. A value that works for Visium may be wrong for Slide-seq or Stereo-seq.

### GraphST

Tune in this order:
1. `epochs`
2. `dim_output`
3. `n_domains`

Guidance:
- For large datasets (`>30k` spots), start with `epochs=50~100`.
- For medium datasets, `epochs=100~200` is a reasonable range.
- Keep `dim_output=64` unless there is a clear reason to increase it.
- Use `--refine` when labels look speckled or spatially noisy.

Important warnings:
- GraphST is not a good first-pass choice for very large datasets unless the user explicitly requests it.
- If raw counts are unavailable, the wrapper falls back to `adata.X`, which is less ideal.

## Step 5: Large-Dataset Rules

For `>30k` spots / cells:
- Prefer **Leiden**, **CellCharter**, or **BANKSY** as the first run.
- Avoid starting with **GraphST**, **SpaGCN**, or **STAGATE** unless the user explicitly wants them.
- If using a deep model, explicitly warn that runtime may be long and reduce `epochs` on the first attempt.

For very uncertain domain count:
- Prefer **CellCharter auto-K** or a **Leiden baseline** first.
- Do not lock into a fixed `n_domains` without a biological rationale.

## Step 6: What To Say After The Run

- If `n_domains > 15`: suggest lowering `--resolution` or `--n-domains`.
- If `n_domains < 3`: suggest raising `--resolution` or `--n-domains`.
- If one domain contains `>60%` of spots: mention possible under-clustering, batch effect, or preprocessing issues.
- If Leiden / Louvain domains are spatially fragmented: suggest increasing `--spatial-weight` or trying CellCharter / BANKSY.
- If GraphST labels are speckled: suggest `--refine` or slightly higher `--epochs`.
- If CellCharter auto-K lands on the search-range boundary: suggest widening or shifting `auto_k_min` / `auto_k_max`.
- If a deep model was very slow: suggest falling back to Leiden or CellCharter for the next iteration.

## Step 6.5: Explain The Visualization Contract Correctly

After a successful run, describe outputs in two layers:

- **Python standard gallery**: this is the canonical OmicsClaw result layer. It should be the first thing users inspect.
- **R customization layer**: this is optional and should consume `figure_data/` exports rather than recomputing domain labels.

Current `spatial-domains` gallery roles are:
- `overview`: spatial and UMAP domain maps
- `diagnostic`: PCA domain view and domain neighbor-mixing heatmap
- `supporting`: domain size summary
- `uncertainty`: local-purity spatial map and histogram

If the user asks for prettier or journal-style figures, point them to:
- `figure_data/domain_spatial_points.csv`
- `figure_data/domain_umap_points.csv`
- `figure_data/domain_counts.csv`
- `figure_data/domain_neighbor_mixing.csv`
- `reproducibility/r_visualization.sh`
