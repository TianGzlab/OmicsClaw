---
name: spatial-domains
description: Load when detecting tissue domains / niches on a preprocessed spatial AnnData via Leiden
  / Louvain (spatial-weighted) or graph-neural backends (SpaGCN / STAGATE / GraphST / BANKSY / CellCharter).
  Skip when ranking spatially variable genes (use spatial-genes); spot-level cell-type annotation (use
  spatial-annotate).
trigger: spatial domain, tissue region, niche, spatial niche, niche identification, niche detection, SpaGCN, STAGATE, CellCharter
tags:
- spatial
- domains
- niches
- spagcn
- stagate
- graphst
- banksy
- cellcharter
- leiden
- louvain
---

# spatial-domains

## When to use

The user has a preprocessed spatial AnnData (`obsm["X_pca"]` and
`obsm["spatial"]` populated) and wants tissue regions / niches
identified per spot (`obs["spatial_domain"]`). Seven methods:

- `leiden` (default) — spatial-weighted Leiden (`--resolution`,
  `--spatial-weight`). No GPU.
- `louvain` — spatial-weighted Louvain. No GPU.
- `spagcn` — graph convolutional, fixed-K (`--n-domains`, `--epochs`,
  `--spagcn-p`). Requires `torch` + `SpaGCN`.
- `stagate` — graph attention with cell-type-aware regularisation
  (`--stagate-alpha`, `--pre-resolution`, `--rad-cutoff` / `--k-nn`).
  Requires `torch` + `torch-geometric`.
- `graphst` — graph-self-supervised (`--epochs`, `--dim-output`,
  `--n-domains`). Auto-detects 10x platform. Requires `torch` +
  `GraphST`.
- `banksy` — neighbourhood expression matrix + PCA (`--lambda-param`,
  `--num-neighbours`). 0.2 = cell-typing mode, 0.8 = domain mode.
- `cellcharter` — niche-graph clustering with auto-k (`--auto-k`,
  `--auto-k-min`/`--auto-k-max`, `--n-layers`). Requires
  `cellcharter` + `pyro-ppl`.

For spatially variable genes use `spatial-genes`; for spot-level
cell-type labels use `spatial-annotate`.

## Inputs & Outputs

**Inputs**

- File types: `.h5ad`
- Expects `obsm`: `spatial`

**Outputs**

- `tables/domain_assignments.csv`
- `tables/domain_counts.csv`
- `tables/domain_method_embedding_points.csv`
- `tables/domain_neighbor_mixing.csv`
- `tables/domain_spatial_points.csv`
- `tables/domain_summary.csv`
- `tables/domain_umap_points.csv`
- `figures/domain_local_purity_histogram.png`
- `figures/domain_local_purity_spatial.png`
- `figures/domain_neighbor_mixing.png`
- `figures/domain_sizes.png`
- `figures/pca_domains.png`
- `figures/spatial_domains.png`
- `figures/umap_domains.png`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `spatial_domain`; `obsm`: `X_stagate`, `X_graphst`, `X_banksy_pca`, `X_cellcharter`

## Flow

1. Load AnnData (`--input`) or build a demo. Auto-compute `obsm["X_pca"]` if missing (logs a warning).
2. Default `--n-domains` to 7 for GNN methods (`spagcn`/`stagate`/`graphst`) and for `cellcharter` when `--auto-k` is off.
3. For `graphst`: infer `--data-type` from input metadata / path (10x Visium auto-detected).
4. Run the chosen method; write `obs["spatial_domain"]` (categorical) and method-specific `obsm` embedding.
5. Optionally refine domain assignments with neighbourhood smoothing (`--refine`).
6. Compute domain counts + proportions; per-domain neighbour-mixing summary.
7. Save tables, figures, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **`--input` missing → `sys.exit(1)` via `print` + `sys.exit`, NOT `parser.error`.** `spatial_domains.py` prints `"ERROR: Provide --input or --demo"` to stderr and `sys.exit(1)` — different from sibling skills' `parser.error`. Caller wrappers expecting `parser.error` (exit 2) get exit 1.
- **`obsm["X_pca"]` is auto-computed when missing.** `spatial_domains.py` logs a warning and runs `sc.pp.pca`. The implicit PCA uses defaults (no HVG selection, no batch correction). For real data prefer `spatial-preprocess` upstream so the PCA reflects HVG-aware preprocessing.
- **GNN methods auto-default `--n-domains` to 7.** `spatial_domains.py` silently sets `args.n_domains = 7` for `spagcn` / `stagate` / `graphst` and for `cellcharter` (when `--auto-k` is off). Override explicitly or these K-fixed methods quietly target 7 clusters.
- **`obsm["spatial"]` ↔ `obsm["X_spatial"]` sync.** `spatial_domains.py` ensures both keys exist (copies one to the other if missing). Some upstream skills only write one; this skill normalises.
- **Per-method `obsm` embedding key.** `spatial_domains.py` records: STAGATE → `obsm["X_stagate"]`, GraphST → `obsm["X_graphst"]`, BANKSY → `obsm["X_banksy_pca"]`, CellCharter → `obsm["X_cellcharter"]`. Leiden / Louvain / SpaGCN do NOT write a method-specific embedding.
- **STAGATE is GitHub-only and never auto-installed.** `STAGATE_pyG` does not exist on PyPI, so `pip install STAGATE-pyG` always fails. `skills/_sdk/deps.py` lists it as a `git` entry, which `install_skill_deps` reports but does not install. Every other method still works; only `--method stagate` raises `ImportError`. To enable it: `pip install git+https://github.com/RucDongLab/STAGATE_pyG.git` (needs `torch` + `torch_geometric`).
- **Performance warning at 30K cells.** `spatial_domains.py` logs a warning when `n_cells > 30000` and method ∈ {`graphst`, `spagcn`, `stagate`}. The methods still run; consider downsampling or switching to `leiden` for large datasets.
- **GraphST is unrecommended above 5K cells.** `spatial_domains.py` logs a separate warning specifically for `graphst` when `n_cells is None or n_cells > 5000`.

## Key CLI

```bash
# Demo (synthetic spatial)
python skills/spatial/spatial-domains/spatial_domains.py --demo --output /tmp/spatial_dom_demo

# Default leiden with spatial weighting
python skills/spatial/spatial-domains/spatial_domains.py \
  --input preprocessed.h5ad --output results/ \
  --method leiden --resolution 1.0 --spatial-weight 0.3

# SpaGCN with explicit K
python skills/spatial/spatial-domains/spatial_domains.py \
  --input preprocessed.h5ad --output results/ \
  --method spagcn --n-domains 8 --spagcn-p 0.5 --epochs 200

# STAGATE with cell-type-aware module
python skills/spatial/spatial-domains/spatial_domains.py \
  --input preprocessed.h5ad --output results/ \
  --method stagate --rad-cutoff 150 --stagate-alpha 0.5 --n-domains 7

# CellCharter with auto-k
python skills/spatial/spatial-domains/spatial_domains.py \
  --input preprocessed.h5ad --output results/ \
  --method cellcharter --auto-k --auto-k-min 4 --auto-k-max 12 --n-layers 3
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins; cell-count rules of thumb
- `references/output_contract.md` — `obs["spatial_domain"]` + per-method `obsm` keys
- Adjacent skills: `spatial-preprocess` (upstream — produces `obsm["X_pca"]` / `obsm["spatial"]`), `spatial-integrate` (upstream — for multi-batch data, run integration first), `spatial-genes` (parallel — spatially variable gene ranking, NOT domain detection), `spatial-annotate` (parallel — spot-level cell-type labels, complementary to domain labels), `spatial-de` (downstream — DE between domains)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `cellcharter`, `GraphST`, `igraph`, `louvain`, `matplotlib`, `numpy`, `pandas`, `pybanksy`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`, `SpaGCN`, `squidpy`, `STAGATE-pyG`, `torch`
