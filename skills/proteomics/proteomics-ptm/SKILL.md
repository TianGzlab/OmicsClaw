---
name: proteomics-ptm
description: Load when summarising PTM sites (phosphorylation, acetylation, ubiquitination, etc.) from
  a per-site CSV — site-class assignment (Olsen et al. Class I/II/III by `localization_probability`),
  per-PTM-type counts, amino-acid distribution, sites-per-protein. Skip when raw spectra are the input;
  you only need protein-level abundance (use proteomics-quantification).
trigger: PTM, phosphorylation, acetylation, ubiquitination, modification, motif
tags:
- proteomics
- ptm
- phosphorylation
- acetylation
- ubiquitination
- site-localization
---

# proteomics-ptm

## When to use

The user has a PTM-site CSV (columns include `protein` and
`ptm_type`, optionally `localization_probability`, `amino_acid`)
and wants per-PTM summary: site-class assignment using
Olsen et al. (2006) thresholds (Class I ≥ `--loc-threshold`,
Class II ≥ 0.50, Class III < 0.50, Unknown if no probability),
per-PTM-type counts, amino-acid distribution, sites-per-protein.

`--loc-threshold` controls the Class I cutoff (default 0.75).

For protein-level abundance (no PTM split) use
`proteomics-quantification`. For DE between conditions use
`proteomics-de`.

## Inputs & Outputs

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/ptm_class_I_sites.csv`
- `tables/ptm_sites.csv`
- `report.md`
- `result.json`

## Flow

1. Load CSV (`--input <ptm_sites.csv>`) or generate a demo (`--demo`).
2. Validate required columns `protein`, `ptm_type` (`proteomics_ptm.py` raises `ValueError("Missing required column: '{col}'")`).
3. If `localization_probability` column exists, classify each site (`proteomics_ptm.py`):
   - Class I: prob ≥ `--loc-threshold` (default 0.75)
   - Class II: prob ≥ 0.50
   - Class III: < 0.50 (default branch)
   - If column missing → `Unknown`
4. Aggregate per-PTM-type counts, amino-acid distribution (optional), sites-per-protein.
5. Write `tables/ptm_sites.csv` (`proteomics_ptm.py`) + `tables/ptm_class_I_sites.csv` + `report.md` + `result.json`.

## Gotchas

- **Required CSV columns are LOWERCASE: `protein`, `ptm_type`.** `proteomics_ptm.py` raises `ValueError("Missing required column: '{col}'")` on first missing column. MaxQuant `Phospho (STY)Sites.txt` uses `Proteins` / `Modification`; rename to lowercase `protein` / `ptm_type` first.
- **Without `localization_probability`, EVERY site is `Unknown`.** `proteomics_ptm.py` falls back to `df["site_class"] = "Unknown"`. The `tables/ptm_class_I_sites.csv` output will then be empty (no Class I sites). For unprocessed search-engine output that lacks the localization-probability column, run a localization tool (e.g. PhosphoRS / Andromeda) upstream.
- **`--input` REQUIRED unless `--demo`.** `proteomics_ptm.py` raises `ValueError("--input required when not using --demo")`.
- **Class II cutoff is HARD-CODED at 0.50.** Only `--loc-threshold` (Class I cutoff) is configurable. The 0.50 boundary at `proteomics_ptm.py` cannot be tuned via CLI.
- **`amino_acid` distribution is optional and key-absent when empty.** Without the `amino_acid` column, the script omits `summary["amino_acid_distribution"]` entirely (the `if aa_counts:` guard at `proteomics_ptm.py` skips the assignment). Downstream consumers should check key presence (`"amino_acid_distribution" in summary`), not just length. Note the actual key name is `amino_acid_distribution` — NOT `aa_counts`.
- **`ptm_type` values are case-sensitive.** `Phospho` and `phospho` are counted as distinct PTM types. Pre-normalise casing if your search engine emits mixed values.

## Key CLI

```bash
# Demo
python skills/proteomics/proteomics-ptm/proteomics_ptm.py --demo --output /tmp/ptm_demo

# Real PTM sites with default Class I threshold
python skills/proteomics/proteomics-ptm/proteomics_ptm.py \
  --input phospho_sites.csv --output results/

# Stricter Class I threshold (0.95)
python skills/proteomics/proteomics-ptm/proteomics_ptm.py \
  --input phospho_sites.csv --output results/ --loc-threshold 0.95
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — Olsen et al. site-class definition, per-PTM caveats
- `references/output_contract.md` — `tables/ptm_sites.csv` + Class I subset schemas
- Adjacent skills: `proteomics-data-import` (upstream — protein-level table normalisation), `proteomics-quantification` (parallel — protein-level abundance, no PTM split), `proteomics-de` (downstream — differential PTM site abundance via two-group test), `proteomics-enrichment` (downstream — pathway enrichment on PTM-target proteins)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
