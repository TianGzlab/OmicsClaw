---
name: bulkrna-deconvolution
description: Load when estimating cell-type proportions in bulk RNA-seq samples from a single-cell or signature-matrix reference. Skip if the data is already single-cell (no deconvolution needed) or for spatial deconvolution (use spatial-deconv).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- deconvolution
- NNLS
- CIBERSORTx
- MuSiC
- cell-type-proportion
---

# bulkrna-deconvolution

## When to use

Run on a bulk RNA-seq cohort when you have a single-cell reference (or
a curated signature matrix) and want to estimate per-sample cell-type
proportions.  Built-in NNLS path is dependency-free; CIBERSORTx and
MuSiC bridges are available when the upstream tools are installed.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Bulk count matrix | `.csv` (gene × sample) | yes (or `--demo`) |
| Reference | `--reference` CSV (signature matrix) or `.h5ad` (sc reference) | yes (or `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Proportions | `tables/cell_type_proportions.csv` | sample × cell_type, rows sum to 1 |
| Stacked-bar plot | `figures/proportions_stacked.png` | per-sample composition |
| Heatmap | `figures/proportions_heatmap.png` | sample × cell_type intensity |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load bulk matrix (`bulkrna_deconvolution.py:368` raises `ValueError` if `--input` missing without `--demo`).
2. Load reference (`:370` raises `ValueError` if `--reference` missing without `--demo`; `:76` raises `FileNotFoundError` if path doesn't exist).
3. Align gene namespaces between bulk and reference (`:131` raises if no overlap).
4. Resolve `--method`: NNLS (built-in), CIBERSORTx (external binary), MuSiC (R bridge).
5. Run deconvolution; optionally normalise rows to sum to 1.
6. Render figures and emit table + report.

## Gotchas

- **`--reference` is REQUIRED for non-demo runs.**  Unlike most bulkrna skills, this one needs two inputs.  `bulkrna_deconvolution.py:370` raises with "--reference is required when not using --demo" if you forget; no silent fallback.
- **Gene-namespace mismatch is fatal.**  `:131` raises `ValueError` when bulk and reference share zero gene IDs (typical cause: bulk uses Ensembl, reference uses HGNC symbols).  Pre-run `bulkrna-geneid-mapping` to harmonise; the error message names the offending sets so cross-checking is easy.
- **CIBERSORTx requires an external binary, not a pip install.**  The CIBERSORTx bridge calls a CLI that must be on `$PATH`; if missing, the run errors with a stack trace pointing at `subprocess` rather than a friendly OmicsClaw message.  Use NNLS unless you specifically need CIBERSORTx's noise-handling.
- **MuSiC requires an R environment.**  Like CIBERSORTx, this is a bridge — no auto-install.  The bridge reads the reference as a `SingleCellExperiment`; the conversion happens via `zellkonverter` and can fail silently if the sc reference has unexpected `obs` columns.  Always verify `result.json["method_used"]` matches `--method`.

## Key CLI

```bash
python omicsclaw.py run bulkrna-deconvolution --demo
python omicsclaw.py run bulkrna-deconvolution \
  --input counts.csv --reference signature.csv --output results/ \
  --method nnls
python omicsclaw.py run bulkrna-deconvolution \
  --input counts.csv --reference scref.h5ad --output results/ \
  --method music
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — NNLS vs CIBERSORTx vs MuSiC, signature matrix construction
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-geneid-mapping` (run upstream to harmonise gene IDs), `bulkrna-trajblend` (parallel: bulk-to-sc bridging via VAE+GNN), `spatial-deconv` (spatial-side sibling: spot-level proportions)
