---
name: sc-gene-programs
description: Load when extracting gene programs (NMF / cNMF factorisation) and per-cell program usage scores from a non-negative scRNA AnnData. Skip when ranking marker genes per cluster (use sc-markers) or for inferring TF → target regulons (use sc-grn).
version: 0.2.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- gene-programs
- nmf
- cnmf
- factorisation
requires:
- anndata
- scanpy
- numpy
- pandas
- scikit-learn
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
(genes × K), `tables/top_program_genes.csv` (top-N genes per program).

For per-cluster marker discovery use `sc-markers`; for TF → target
regulons use `sc-grn`; for per-cell pathway scores against curated
gene sets use `sc-pathway-scoring`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Non-negative AnnData | `.h5ad` (raw counts in `layers["counts"]` or log-normalised in `.X`) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | adds `obsm["X_gene_programs"]` (cells × K usage matrix; `sc_gene_programs.py:469`). The `program_usage` name only applies to the `tables/program_usage.csv` file, NOT to the obsm key. |
| Per-cell usage | `tables/program_usage.csv` | cells × K matrix |
| Gene weights | `tables/program_weights.csv` | genes × K matrix |
| Top genes | `tables/top_program_genes.csv` | top-`--top-genes` per program |
| Figures | `figures/mean_program_usage.png`, `figures/program_correlation.png` | always |
| Report | `report.md` + `result.json` | always |

## Flow

1. Auto-fallback check: try `import cnmf`; if it fails, silently switch `--method` to `nmf`.
2. Load AnnData (`--input`) or build a demo.
3. Preflight: pick source matrix per `--layer` (auto-prefer `layers["counts"]` for cnmf when `--layer` is unset); reject negative values; warn if `n_genes < 50` or running NMF on raw counts without `--layer counts`.
4. Run cNMF (consensus NMF with `--n-iter` runs) or sklearn NMF (single run, `--seed`).
5. Build top-genes-per-program table; compute per-program correlation matrix.
6. Detect degenerate output → record diagnostics; do NOT raise.
7. Save tables, figures, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **`cnmf` silently auto-falls back to `nmf` if cnmf is not installed.** `sc_gene_programs.py:407-409` catches `ImportError` from `import cnmf`, logs a warning, sets `args.method = "nmf"` (so `summary["method"]` at `:527` already reflects the post-fallback value). `summary["backend"]` at `:528` records the same. Inspect either before quoting "we used cNMF".
- **Negative values reject the run.** `sc_gene_programs.py:132` raises `SystemExit("NMF/cNMF requires non-negative input, but the data matrix contains negative values. This usually means the data has been z-score scaled. ...")` with a multi-option fix message. Most common cause: feeding a `sc.pp.scale`-d AnnData where `.X` is mean-centred. Pass `--layer counts` or re-run `sc-preprocessing` without scaling.
- **`cnmf` auto-prefers `layers["counts"]`; nmf doesn't.** `sc_gene_programs.py:111-112` switches to `layers["counts"]` for cnmf if `--layer` is unset and the layer exists. nmf without `--layer` uses `.X` directly. If your raw counts live elsewhere, pass `--layer <name>` explicitly to avoid silent fallback to `.X`.
- **Missing `--layer` value also `SystemExit`s.** `sc_gene_programs.py:118` raises `SystemExit("Layer '<name>' not found in adata.layers. Available layers: <list>. ...")` when an explicit `--layer` doesn't resolve. Wrappers expecting `ValueError` need to catch `SystemExit`.
- **`--input` mandatory unless `--demo`.** `sc_gene_programs.py:418` raises `SystemExit("Provide --input or use --demo")`.
- **Degenerate output is a soft fail.** When the factorisation collapses to fewer effective programs than `--n-programs`, `sc_gene_programs.py:533-534` records `summary["degenerate_output"] = True` and lists `degenerate_issues` — but the script returns 0. Always inspect `result.json["n_programs"]` (line 529, the *effective* count) before chaining downstream.

## Key CLI

```bash
# Demo (cNMF on synthetic data, falls back to NMF if cnmf missing)
python omicsclaw.py run sc-gene-programs --demo --output /tmp/sc_gp_demo

# cNMF with 8 programs on raw counts
python omicsclaw.py run sc-gene-programs \
  --input clustered.h5ad --output results/ \
  --method cnmf --n-programs 8 --n-iter 200 --layer counts

# NMF on log-normalised .X (faster, less stable)
python omicsclaw.py run sc-gene-programs \
  --input normalized.h5ad --output results/ \
  --method nmf --n-programs 10 --top-genes 50
```

## See also

- `references/parameters.md` — every CLI flag, NMF / cNMF tunables
- `references/methodology.md` — when consensus NMF wins; layer-selection guide
- `references/output_contract.md` — `obsm["X_gene_programs"]` / `tables/program_*.csv` schemas
- Adjacent skills: `sc-preprocessing` (upstream — produces a non-negative `.X` or `layers["counts"]`), `sc-markers` (parallel — cluster markers, NOT latent factors), `sc-pathway-scoring` (parallel — supervised program scoring against curated gene sets), `sc-grn` (parallel — TF → target regulons; complementary to gene programs)
