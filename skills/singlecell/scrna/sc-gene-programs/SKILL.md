---
name: sc-gene-programs
description: Load when extracting gene programs (NMF / cNMF factorisation) and per-cell program usage
  scores from a non-negative scRNA AnnData. Skip when ranking marker genes per cluster (use sc-markers);
  inferring TF → target regulons (use sc-grn).
tags:
- singlecell
- scrna
- gene-programs
- nmf
- cnmf
- factorisation
---

# sc-gene-programs

## When to use

The user has a non-negative scRNA AnnData (raw counts or log-normalised
expression) and wants to decompose it into K gene programs (latent
factors) plus a per-cell usage matrix. Two methods:

- `cnmf` (default) — consensus NMF (multiple runs + clustering of
  factors) for stable programs. Auto-falls back to `nmf` if the `cnmf`
  package isn't installed.
- `nmf` — sklearn NMF, single run.

Output: `tables/program_usage.csv` (cells × K), `tables/program_weights.csv`
(programs × genes), `tables/top_program_genes.csv` (top-N genes per program).

For per-cluster marker discovery use `sc-markers`; for TF → target
regulons use `sc-grn`; for per-cell pathway scores against curated
gene sets use `sc-pathway-scoring`.

## Use in an analysis step

Use `load_skill` from the notebook SDK; write returned objects with
`write_output`. This runnable example is also in `examples/example_step.py`.
The CLI remains available for standalone reports and galleries.

```python
# Extract six NMF programs from the log-normalized PBMC68k snapshot.
# Reads pbmc68k_reduced.
# Calls sc-gene-programs: find_programs, top_program_genes, usage_figure.

from skills._sdk.notebook import load_demo, load_skill, write_output

programs = load_skill('sc-gene-programs')
adata = load_demo('pbmc68k_reduced').raw.to_adata()

result = programs.find_programs(adata, method='nmf')
top = programs.top_program_genes(result, n=10)
write_output(result, 'intermediate/programs.h5ad')
write_output(top, 'tables/top_program_genes.csv')
write_output(programs.usage_figure(result), 'figures/program_usage.png')

assert result.obsm['X_gene_programs'].shape == (adata.n_obs, 6)
assert (result.obsm['X_gene_programs'] >= 0).all()
assert top['program'].nunique() == 6
assert set(top.gene).issubset(adata.var_names)
```

## Inputs & Outputs

Input is a non-negative AnnData expression matrix; `layer` selects another
matrix. PCA and neighbors are not required. `find_programs` returns a copy
with `obsm["X_gene_programs"]` and tables exposed by the API helpers.

The CLI writes `processed.h5ad`, `report.md`, `result.json`,
`tables/program_usage.csv` (cells × programs),
`tables/program_weights.csv` (programs × genes), and
`tables/top_program_genes.csv`. cNMF additionally writes
`tables/program_tpm.csv`. Gallery figures are `mean_program_usage.png`
and, for multiple programs, `program_correlation.png`. Figure source
tables, including program correlations, live under `figure_data/`.

## Flow

1. Auto-fallback check: try `import cnmf`; if it fails, switch to `nmf` and record the fallback.
2. Load AnnData (`--input`) or build a demo.
3. Preflight: pick source matrix per `--layer` (auto-prefer `layers["counts"]` for cnmf when `--layer` is unset); reject negative values; warn if `n_genes < 50` or running NMF on raw counts without `--layer counts`.
4. Run cNMF (consensus NMF with `--n-iter` iterations per factorization) or sklearn NMF (single run, `--seed`).
5. Build top-genes-per-program table; compute per-program correlation matrix.
6. Detect degenerate output → record diagnostics; do NOT raise.
7. Save tables, figures, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- `run_info(result)` records requested and executed methods and the reason when missing cNMF falls back to sklearn NMF. CLI `result.json["summary"]["backend"]` reports the executed backend.
- CLI preflight rejects negative input. The API retains the existing solver's negative-to-zero clipping; use a non-negative matrix for interpretable `program_weights`.
- cNMF prefers `layers["counts"]` when `layer` is unset; NMF uses X. A missing cNMF backend falls back to NMF's matrix selection.
- `n_iter` / `--n-iter` is the maximum number of iterations per factorization, not the number of consensus replicates. `run_info` includes the cNMF replicate count when used.
- CLI `result.json["summary"]["degenerate_output"]` reports collapsed programs without making the run fail. Inspect the flag and `degenerate_issues` before using the tables.

## Key CLI

```bash
# Demo (cNMF on synthetic data, falls back to NMF if cnmf missing)
python skills/singlecell/scrna/sc-gene-programs/sc_gene_programs.py --demo --output /tmp/sc_gp_demo

# cNMF with 8 programs on raw counts
python skills/singlecell/scrna/sc-gene-programs/sc_gene_programs.py \
  --input clustered.h5ad --output results/ \
  --method cnmf --n-programs 8 --n-iter 200 --layer counts

# NMF on log-normalised .X (faster, less stable)
python skills/singlecell/scrna/sc-gene-programs/sc_gene_programs.py \
  --input normalized.h5ad --output results/ \
  --method nmf --n-programs 10 --top-genes 50
```

## See also

- `references/parameters.md` — every CLI flag, NMF / cNMF tunables
- `references/methodology.md` — when consensus NMF wins; layer-selection guide
- `references/output_contract.md` — `obsm["X_gene_programs"]` / `tables/program_*.csv` schemas
- Adjacent skills: `sc-preprocessing` (upstream — produces a non-negative `.X` or `layers["counts"]`), `sc-markers` (parallel — cluster markers, NOT latent factors), `sc-pathway-scoring` (parallel — supervised program scoring against curated gene sets), `sc-grn` (parallel — TF → target regulons; complementary to gene programs)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `cnmf`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scikit-learn`, `scipy`

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `find_programs(adata, *, method: str='cnmf', n_programs: int=6, n_iter: int=400, layer: str | None=None, top_genes: int=30, random_state: int=0)`

Return a copy with per-cell usage in obsm['X_gene_programs'].

cNMF uses counts when available; missing cNMF falls back to sklearn NMF,
recorded by run_info. NMF uses X unless layer is set. Negative values are
clipped to zero by the existing solver. n_iter limits each factorization's
iterations, not the number of cNMF replicates. Both methods use random_state.
Program weights and ranked genes are available through the table helpers.

### `program_weights(adata) -> pd.DataFrame`

Return program-by-gene weights from find_programs.

### `top_program_genes(adata, *, n: int | None=None) -> pd.DataFrame`

Return ranked genes and weights; n optionally limits genes per program.

### `program_correlation(adata) -> pd.DataFrame`

Return Pearson correlations between per-cell program usages.

### `usage_figure(adata)`

Return a heatmap figure of cells by program usage, without writing files.

### `run_info(adata, *, keep: bool=True) -> dict`

Return methods and solver diagnostics; keep=False removes the run record.

<!-- api:end -->
