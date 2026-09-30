---
name: proteomics-quantification
description: Load when computing per-protein abundance from a peptide / PSM table via LFQ (intensity summation),
  iBAQ (intensity / tryptic peptide count), or spectral counting (PSMs per protein). Skip when the input
  is already protein-level (use proteomics-ms-qc); label-based TMT / iTRAQ workflows (search upstream
  first).
trigger: protein quantification, LFQ, TMT, DIA, DIA-NN, Skyline
tags:
- proteomics
- quantification
- lfq
- ibaq
- spectral-counting
---

# proteomics-quantification

## When to use

The user has a peptide / PSM table and wants protein-level
abundance via one of:

- `lfq` (default) — Label-Free Quantification by intensity
  summation. Requires an `intensity` column.
- `ibaq` — intensity-Based Absolute Quantification
  (intensity / theoretical tryptic peptide count). Requires an
  `intensity` column AND ONE OF: a per-protein `sequence` column
  (in-silico digested by the script) OR a pre-computed
  `n_theoretical_peptides` integer column. Without either, the
  script silently estimates `unique_peptides × 1.5`.
- `spectral_count` — PSM count per protein (no intensity needed).

Pick with `--method {lfq,spectral_count,ibaq}` (default `lfq`).
For TMT / iTRAQ label-based workflows, perform the search-engine
quant first; this skill is intensity- / count-only.

## Inputs & Outputs

**Inputs**

- Modalities: lfq
- File types: `.csv`
- Accepts artifact `proteomics.peptide_table` (`csv`)

**Outputs**

- `tables/protein_abundance.csv`
- `report.md`
- `result.json`
- Produces artifact `proteomics.abundance_matrix` as `tables/protein_abundance.csv` (`csv`)

## Flow

1. Load CSV (`--input <peptides.csv>`) or generate a demo (`--demo`).
2. Dispatch on `--method` (`proteomics_quantification.py`); validate required columns per method.
3. Aggregate per protein:
   - `lfq`: sum `intensity` per protein.
   - `ibaq`: sum `intensity` per protein, divide by `n_theoretical_peptides`. Source order at `proteomics_quantification.py`: `sequence` (compute on the fly) → `n_theoretical_peptides` (use as-is) → `unique_peptides × 1.5` (silent estimate with warning).
   - `spectral_count`: count PSMs per protein.
4. Write `tables/protein_abundance.csv` (`proteomics_quantification.py`) + `report.md` + `result.json`.

## Gotchas

- **`lfq` and `ibaq` require an `intensity` column; method enforces this.** `proteomics_quantification.py` raises `ValueError("Input requires an 'intensity' column for LFQ")`; raises the same for iBAQ. `spectral_count` only needs row counts (no intensity).
- **`ibaq` requires either `sequence` OR `n_theoretical_peptides`; otherwise it SILENTLY ESTIMATES.** `proteomics_quantification.py` checks for `sequence` first (in-silico digest, K/R not before P, length 7-30), then `n_theoretical_peptides`, otherwise falls back to `unique_peptides × 1.5` with only a logger warning. The wrong column name (`theoretical_peptides` instead of `n_theoretical_peptides`) silently triggers the estimate path — always pass one of the two correct columns.
- **Unknown `--method` raises `ValueError`.** `proteomics_quantification.py` rejects values outside `("lfq", "spectral_count", "ibaq")`. The `argparse choices=` already enforces this — the `_dispatch_method` raise is defence-in-depth for direct library calls.
- **`--input` REQUIRED unless `--demo`.** `proteomics_quantification.py` raises `ValueError("--input required")`.
- **Missing intensities in `lfq` are summed as 0.** `pd.Series.sum(skipna=True)` is the default — proteins with all-NaN intensities yield 0, indistinguishable from "all detected as zero". Pre-filter or impute upstream if NaN-vs-zero matters.

## Key CLI

```bash
# Demo (LFQ default)
python skills/proteomics/proteomics-quantification/proteomics_quantification.py --demo --output /tmp/quant_demo

# LFQ on real peptides
python skills/proteomics/proteomics-quantification/proteomics_quantification.py \
  --input peptides.csv --output results/ --method lfq

# iBAQ via per-protein sequence (in-silico digest)
python skills/proteomics/proteomics-quantification/proteomics_quantification.py \
  --input peptides_with_sequence.csv --output results/ --method ibaq

# iBAQ via pre-computed n_theoretical_peptides
python skills/proteomics/proteomics-quantification/proteomics_quantification.py \
  --input peptides_with_n_theo.csv --output results/ --method ibaq

# Spectral counting
python skills/proteomics/proteomics-quantification/proteomics_quantification.py \
  --input psms.csv --output results/ --method spectral_count
```

## See also

- `references/parameters.md` — every CLI flag, per-method input requirements
- `references/methodology.md` — LFQ / iBAQ / spectral-count semantics
- `references/output_contract.md` — `tables/protein_abundance.csv` schema
- Adjacent skills: `proteomics-data-import` (upstream — produces normalised peptide / protein tables), `proteomics-identification` (upstream — peptide-level summary), `proteomics-ms-qc` (parallel — protein-table QC), `proteomics-de` (downstream — differential abundance)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
