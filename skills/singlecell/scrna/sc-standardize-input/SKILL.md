---
name: sc-standardize-input
description: Load when an external single-cell h5ad/h5/loom/mtx needs to be canonicalised onto the OmicsClaw AnnData contract before downstream scRNA skills run. Skip when data already came from sc-count (already canonical), or for bulk RNA-seq (use bulkrna-qc) or spatial (use spatial-preprocess).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- input
- standardization
- anndata
requires:
- anndata
- numpy
- scipy
---

# sc-standardize-input

## When to use

The user has a single-cell expression file from outside OmicsClaw (a public
`.h5ad`, a 10X mtx directory, a `.loom`, etc.) and needs the canonical
AnnData contract every downstream scRNA skill assumes: raw counts in
`layers["counts"]` and `adata.raw`, harmonised feature names, and a
`uns["omicsclaw_matrix_contract"]` provenance record.  Run this once before
`sc-qc` / `sc-preprocessing` / etc.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Single-cell expression | `.h5ad`, `.h5`, `.loom`, `.csv`, `.tsv`, or 10X mtx dir | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Canonicalised AnnData | `processed.h5ad` | `adata.X` = counts; `layers["counts"]` + `adata.raw` populated |
| Provenance | `result.json` | `summary` includes `warnings`, contract metadata |
| Report | `report.md` | always written |

## Flow

1. Load via the shared multi-format single-cell loader.
2. Pre-flight: validate non-empty input; auto-detect species from gene name case (UPPER → human, Title → mouse).
3. Pick the best count-like matrix among `layers["counts"]`, `adata.raw`, and `adata.X` (orchestrated by `canonicalize_singlecell_adata` in `skills/singlecell/_lib/adata_utils.py:389`, which calls the `matrix_looks_count_like` heuristic at `_lib/adata_utils.py:255`).
4. Harmonise feature names (Ensembl ↔ symbol, deduplicate).
5. Persist `uns["omicsclaw_input_contract"]` + `uns["omicsclaw_matrix_contract"]`.
6. Save `processed.h5ad`; emit `report.md` + `result.json`.

## Gotchas

- **`--r-enhanced` is accepted but produces no R plots.** `sc_standardize_input.py:250` declares the flag for CLI consistency; this skill is input canonicalisation, not visualisation.  Pass it freely, but expect no R Enhanced figures.
- **Count-source selection is heuristic, not declarative.** The skill scans `layers["counts"]` → `adata.raw` → `adata.X` and picks the first that passes a `matrix_looks_count_like` check.  If the input is already log-normalised everywhere, the heuristic can mis-classify and fall through to `adata.X`; verify `result.json["summary"]["warnings"]` after every run.
- **Species auto-detect is gene-case-based.** UPPER-case symbols → human, Title-case → mouse.  Non-standard gene-name conventions (Ensembl IDs only, lowercase) silently fall through to the `auto` default.  Pass `--species human` or `--species mouse` explicitly when working with non-symbol matrices.
- **No filtering, no normalisation, no clustering.** Even if `result.json` looks complete, the output is still raw counts in canonical form — run `sc-qc` and `sc-preprocessing` next.

## Key CLI

```bash
# Demo (built-in PBMC3K)
python omicsclaw.py run sc-standardize-input --demo --output /tmp/sc_std_demo

# Real run with species hint
python omicsclaw.py run sc-standardize-input \
  --input external.h5ad --output results/ --species mouse
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — count-source heuristic, species detection logic
- `references/output_contract.md` — exact `processed.h5ad` + `result.json` shape
- Adjacent skills: `sc-count` (FASTQ → AnnData; skip standardisation when used), `sc-qc` (next step), `sc-preprocessing` (full normalise+cluster pipeline)
