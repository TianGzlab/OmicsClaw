---
doc_id: skill-guide-spatial-statistics
title: OmicsClaw Skill Guide — Spatial Statistics
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-statistics, statistics]
search_terms: [spatial statistics, Moran, Geary, Ripley, neighborhood enrichment, co-occurrence, local Moran, Getis-Ord, bivariate Moran, centrality]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Statistics

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-statistics` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:

- whether the user is asking a **cluster-level**, **gene-level**, or
  **graph-level** spatial-statistics question
- which graph parameters matter first for the chosen method
- how to explain local hotspot methods without over-claiming them as global
  inference

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:

- **Spatial coordinates**: `obsm["spatial"]` is required for every method here.
- **Cluster labels**: `obs[cluster_key]` is required for neighborhood
  enrichment, Ripley, co-occurrence, and spatial centrality.
- **Expression representation**: current OmicsClaw uses `adata.X` for Moran,
  Geary, local Moran, Getis-Ord, and bivariate Moran.
- **Question type**:
  - cluster adjacency or segregation: `neighborhood_enrichment`
  - clustering / dispersion across distance: `ripley`
  - pairwise proximity curves: `co_occurrence`
  - ranked gene-level global spatial structure: `moran` or `geary`
  - hotspot / coldspot maps: `local_moran` or `getis_ord`
  - spatial cross-correlation of two genes: `bivariate_moran`
  - graph shape / graph position: `network_properties` or `spatial_centrality`

Important implementation notes in current OmicsClaw:

- Graph-based methods reuse an existing `spatial_connectivities` graph by
  default.
- If the user changes `stats_n_neighs` or `stats_n_rings`, OmicsClaw rebuilds
  the graph to honor that request.
- If the default `cluster_key=leiden` is missing and the method requires it,
  OmicsClaw can run a minimal clustering pass to create it.
- `spatial_centrality` keeps the actual Squidpy score contract:
  `degree_centrality`, `average_clustering`, and `closeness_centrality`.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not already chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|---|---|---|---|
| **Neighborhood enrichment** | Cluster pair enrichment / segregation | `cluster_key=leiden`, `stats_n_neighs=6`, `stats_n_rings=1`, `stats_n_perms=199` | Entire conclusion depends on the chosen graph |
| **Ripley** | Ask whether a cluster is spatially clustered or dispersed across scales | `ripley_mode=L`, `ripley_n_simulations=100`, `ripley_n_steps=50` | Scale-sensitive; do not interpret from one radius only |
| **Co-occurrence** | Compare pairwise proximity across distance bins | `coocc_interval=50` | Descriptive curve, not a gene-level test |
| **Moran** | Rank genes by global positive / negative spatial autocorrelation | `n_top_genes=20`, `stats_n_neighs=6`, `stats_n_perms=199`, `stats_corr_method=fdr_bh` | Result changes with graph and gene selection |
| **Geary** | Alternative global autocorrelation emphasizing local dissimilarity | same as Moran | Do not oversell as an independent validation family |
| **Local Moran** | Find local hotspot / coldspot structure for one or a few genes | `n_top_genes=20`, `stats_n_perms=199` | Local quadrants are easy to over-interpret |
| **Getis-Ord** | Hotspot / coldspot detection with Gi* | `n_top_genes=20`, `stats_n_perms=199`, `getis_star=true` | Also local, not a global ranking method |
| **Bivariate Moran** | Test spatial cross-correlation between exactly two genes | `genes=geneA,geneB`, `stats_n_perms=199` | Requires exactly two genes and answers a narrow question |
| **Network properties** | Summarize graph topology | `stats_n_neighs=6`, `stats_n_rings=1` | Mostly describes graph construction, not biology alone |
| **Spatial centrality** | Compare cluster placement inside the graph | `cluster_key=leiden`, `centrality_score=all` | Centrality is graph-position summary, not mechanism |

Practical default decision order:

1. If the user is asking about **cluster mixing or segregation**, start with
   **neighborhood enrichment**.
2. If the user is asking about **gene spatial structure across the tissue**,
   start with **Moran**.
3. If the user wants **discrete local hotspots**, choose **local Moran** or
   **Getis-Ord** instead of a global autocorrelation method.
4. If the user is actually asking about the **graph itself**, use
   **network properties** or **spatial centrality**.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial statistics
  Method: Moran
  Genes: EPCAM, VIM, CD3D
  Graph: stats_n_neighs=6, stats_n_rings=1 (reuse existing graph if compatible)
  Parameters: stats_n_perms=199, stats_corr_method=fdr_bh, stats_two_tailed=false
```

## Step 4: Method-Specific Tuning Rules

### Neighborhood Enrichment

Tune in this order:

1. `cluster_key`
2. `stats_n_neighs`
3. `stats_n_rings`
4. `stats_n_perms`

Guidance:

- Start with `cluster_key=leiden` or an existing biological annotation column.
- Keep `stats_n_neighs=6`, `stats_n_rings=1` as the first pass unless the user
  explicitly wants a broader neighborhood.
- Increase `stats_n_perms` when the user wants a heavier null model.

Important warning:

- A new graph can change the sign and magnitude of pairwise enrichment results.

### Ripley

Tune in this order:

1. `cluster_key`
2. `ripley_mode`
3. `ripley_n_simulations`
4. `ripley_n_steps`
5. `ripley_max_dist`

Guidance:

- Keep `ripley_mode=L` for the first pass.
- Use more simulations when the user wants a more stable null estimate.
- Only shrink `ripley_max_dist` when the question is explicitly about short
  spatial scales.

Important warning:

- Do not summarize a Ripley result using only one point on the curve.

### Co-occurrence

Tune in this order:

1. `cluster_key`
2. `coocc_interval`
3. `coocc_n_splits`

Guidance:

- Keep `coocc_interval=50` for a first pass.
- Increase the interval count when the user wants finer-grained distance bins.

Important warning:

- Co-occurrence is descriptive; do not talk about it as if it were a gene-level
  statistical test.

### Moran / Geary

Tune in this order:

1. `genes` or `n_top_genes`
2. `stats_n_neighs`
3. `stats_n_rings`
4. `stats_n_perms`
5. `stats_corr_method`

Guidance:

- Use `genes` when the user already has a candidate panel.
- Use `n_top_genes` when the user wants a screening-style first pass.
- Keep `stats_corr_method=fdr_bh` for routine use.
- Use `stats_two_tailed=true` only when the user explicitly wants both strong
  positive and strong negative structure treated symmetrically.

Important warnings:

- Moran and Geary are graph-dependent.
- Do not present Moran and Geary as two independent datasets worth of evidence.

### Local Moran

Tune in this order:

1. `genes` or `n_top_genes`
2. `stats_n_neighs`
3. `stats_n_rings`
4. `stats_n_perms`
5. `local_moran_geoda_quads`

Guidance:

- Prefer a short gene list; local methods are easiest to interpret on targeted
  genes.
- Keep `local_moran_geoda_quads=false` unless the user needs the GeoDa
  quadrant convention specifically.

Important warning:

- A high count of significant spots can reflect graph choice as much as biology.

### Getis-Ord

Tune in this order:

1. `genes` or `n_top_genes`
2. `stats_n_neighs`
3. `stats_n_rings`
4. `stats_n_perms`
5. `getis_star`

Guidance:

- Keep `getis_star=true` for the default Gi* path.
- Use a short gene list when the user is asking about known markers or programs.

Important warning:

- Hotspot counts should be reported as local spatial concentration, not as DE.

### Bivariate Moran

Tune in this order:

1. `genes` (exactly two)
2. `stats_n_neighs`
3. `stats_n_rings`
4. `stats_n_perms`

Guidance:

- Refuse to improvise gene pairs. Ask for or derive a concrete pair from the
  user's stated hypothesis.

Important warning:

- Bivariate Moran is spatial cross-correlation, not a causal interaction model.

### Network Properties / Spatial Centrality

Tune in this order:

1. `stats_n_neighs`
2. `stats_n_rings`
3. `cluster_key` / `centrality_score`

Guidance:

- Keep graph settings conservative for the first pass because topology outputs
  mostly reflect the graph contract.
- Use `centrality_score=all` unless the user wants one score family
  specifically.

Important warning:

- Do not compare centrality values across runs built from different graphs as if
  they were directly commensurate.

## Step 5: Graph Rules

Use this decision order:

1. If the existing graph is acceptable, reuse it and say so explicitly.
2. If the user changes `stats_n_neighs` or `stats_n_rings`, tell them OmicsClaw
   will rebuild the graph.
3. When comparing methods, keep the graph fixed if the user wants a fair
   side-by-side comparison.

## Step 6: What To Say After The Run

- If neighborhood enrichment flips after a graph change: say the result is
  graph-sensitive before offering biological interpretation.
- If Moran / Geary return few significant genes: mention gene selection,
  weak spatial structure, or a graph that may be too local.
- If local methods produce many hotspots: suggest checking whether the graph is
  too broad before over-interpreting the biology.
- If centrality is dominated by one cluster: mention that this is a graph
  placement summary, not automatically a biological hub claim.

## Step 7: Explain Results Using Method-Correct Language

When summarizing results to the user:

- For **neighborhood enrichment**, say cluster-pair enrichment or segregation.
- For **Ripley**, say clustering / dispersion across spatial scales.
- For **co-occurrence**, say pairwise distance-binned proximity.
- For **Moran / Geary**, say global gene-level spatial autocorrelation.
- For **local Moran / Getis-Ord**, say local hotspot / coldspot structure.
- For **bivariate Moran**, say spatial cross-correlation between two genes.
- For **network properties / spatial centrality**, say graph topology or graph
  position.

Do **not** flatten all of these into generic "spatial significance" language.
