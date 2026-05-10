---
name: proteomics-identification
description: Load when summarising peptide identifications (PSM count, unique peptide count, distinct protein count, score / charge distributions) from a peptide-level CSV produced by MaxQuant / FragPipe / DIA-NN. Skip when raw spectra are the input (run a search engine first) or when working with protein-quantification tables (use `proteomics-ms-qc`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- proteomics
- identification
- peptides
- psm
- maxquant
- msgf
requires:
- pandas
- numpy
---

# proteomics-identification

## When to use

The user has a peptide-level CSV (from MaxQuant `peptides.txt`,
FragPipe `combined_peptide.tsv`, DIA-NN, or any peptide table with
columns including `peptide` / `protein` / optionally `score` /
`charge`) and wants identification summary statistics: total PSM
count, unique peptide count, distinct protein count, optional
median score, optional charge distribution.

This skill does NOT run a search engine — it summarises a peptide
table that already exists. The `--fdr` flag is recorded as
metadata only (no FDR re-thresholding is performed).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Peptide table | `.csv` with at least `peptide` and `protein` columns; optional `score`, `charge`, and any one of `qvalue` / `q-value` / `q_value` / `PEP` / `pep` / `fdr` for FDR filtering | yes (unless `--demo`) |
| FDR cutoff | `--fdr <float>` (default 0.01, ACTIVELY filters when an FDR column exists) | no |
| Spectra count | `--n-spectra <int>` (demo size hint only — not a CSV column) | no |

| Output | Path | Notes |
|---|---|---|
| Peptides | `tables/peptides.csv` | FDR-filtered peptide table |
| Report | `report.md` + `result.json` | `summary["n_psms"]`, `summary["n_unique_peptides"]`, `summary["n_proteins"]`, `summary["id_rate"]`; `summary["median_score"]` (if `score` present); `summary["charge_distribution"]` (if `charge` present) |

## Flow

1. Load CSV (`--input <peptides.csv>`) or generate a demo peptide table (`--demo`).
2. Filter by FDR via `filter_by_fdr` (`proteomics_identification.py:105-126`) — searches columns in order `qvalue` → `q-value` → `q_value` → `PEP` → `pep` → `fdr`; if NONE found, logs a warning at `:117` and passes through unchanged.
3. Compute n_psms, n_unique_peptides, n_proteins, id_rate; optionally median `score` (`proteomics_identification.py:147`) and `charge` distribution (`:151`).
4. Write `tables/peptides.csv` (`proteomics_identification.py:235`) + `report.md` + `result.json` (`:241`).

## Gotchas

- **No search engine is invoked.** This skill summarises an existing peptide CSV — it does NOT run MaxQuant / MS-GF+ / Comet / Mascot. Run a search engine upstream and feed the peptide-level CSV here.
- **`--fdr` ACTIVELY filters when an FDR column is present.** `proteomics_identification.py:229` calls `filter_by_fdr(peptides, fdr_threshold=args.fdr)`. The helper (`:105-126`) tries columns in order `qvalue` → `q-value` → `q_value` → `PEP` → `pep` → `fdr`. With NONE present, the run only logs a warning at `:117` and passes the input through unchanged.
- **`--input` REQUIRED unless `--demo`.** `proteomics_identification.py:223` raises `ValueError("--input required when not using --demo")`.
- **Optional columns are silently skipped when absent.** A CSV without `score` omits `summary["median_score"]`; without `charge` omits `summary["charge_distribution"]`. Inspect the JSON before writing downstream consumers that assume those keys exist.
- **Column names must match exactly (lowercase): `peptide`, `protein`, `score`, `charge`.** MaxQuant `evidence.txt` ships with `Sequence` / `Proteins` / `Score` / `Charge` — rename to lowercase first (e.g. `df.rename(columns={"Sequence": "peptide", "Proteins": "protein", "Score": "score", "Charge": "charge"})`).

## Key CLI

```bash
# Demo
python omicsclaw.py run proteomics-identification --demo --output /tmp/id_demo

# Real peptide CSV
python omicsclaw.py run proteomics-identification \
  --input peptides.csv --output results/ --fdr 0.01
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — PSM / peptide / protein semantics, FDR conventions
- `references/output_contract.md` — `tables/peptides.csv` schema
- Adjacent skills: `proteomics-data-import` (upstream — protein-level table normalisation), `proteomics-ms-qc` (parallel — protein-table QC), `proteomics-quantification` (downstream — LFQ / iBAQ / spectral count), `proteomics-de` (downstream — differential abundance)
