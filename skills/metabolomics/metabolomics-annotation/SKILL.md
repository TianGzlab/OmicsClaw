---
name: metabolomics-annotation
description: Load when annotating LC-MS features against a built-in 15-metabolite HMDB demo dictionary
  by m/z within a `--ppm` tolerance — emits a per-feature annotation table. Skip when needing real HMDB
  / KEGG / LipidMaps / METLIN look-up (this skill is demo-only); raw spectra (use metabolomics-xcms-preprocessing).
trigger: metabolite annotation, SIRIUS, GNPS, MetFrag, spectral matching, metabolite ID, ppm tolerance
tags:
- metabolomics
- annotation
- hmdb
- demo
- mz-match
---

# metabolomics-annotation

## When to use

The user has a feature table with `mz` (m/z) values and wants
each feature annotated by m/z match to a metabolite database.
**This is demo-only annotation.** The reference is an 15-entry
HMDB dictionary (`metabolomics_annotation.py`: e.g. Glucose,
Lactic acid, Alanine, Pyruvic acid, Citric acid, Tryptophan).
`--database {hmdb,kegg,lipidmaps,metlin}` is recorded as metadata
but does NOT switch the lookup table.

For real database-scale annotation use SIRIUS / GNPS / MetFrag
externally and feed the resulting annotation CSV into a downstream
skill.

## Inputs & Outputs

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/annotations.csv`
- `report.md`
- `result.json`

## Flow

1. Load CSV (`--input <features.csv>`) or generate a demo (`--demo`).
2. For each input `mz`, search the 15-entry HMDB dictionary (`metabolomics_annotation.py`) within `--ppm` tolerance.
3. Write `tables/annotations.csv` (`metabolomics_annotation.py`) + `report.md` + `result.json`.

## Gotchas

- **Database is HARD-CODED 15 metabolites — `--database` is metadata only.** `metabolomics_annotation.py` defines an 15-entry HMDB tuple. The CLI accepts `hmdb` / `kegg` / `lipidmaps` / `metlin` (choices=...) but the value is only logged into `result.json` — the lookup always uses the same 15-entry HMDB list. For real annotation, use SIRIUS / GNPS / MetFrag externally.
- **`--ppm 10.0` default is m/z-tolerance.** Suitable for high-resolution Orbitrap; for low-resolution Q-TOF use `--ppm 30.0`. The mass-error formula is `|mz_obs - mz_ref| < (ppm × mz_ref / 1e6)`.
- **`--input` REQUIRED unless `--demo`.** `metabolomics_annotation.py` raises `ValueError("--input required when not using --demo")`.
- **Required CSV column is `mz`** (lowercase). XCMS exports `mzmed`, MZmine exports `m/z`; rename to `mz` first.
- **Multiple matches per feature ⇒ multiple rows.** A feature with 3 candidate matches yields 3 rows in `tables/annotations.csv`; deduplicate downstream by `feature_id` if you need 1:1.

## Key CLI

```bash
# Demo
python skills/metabolomics/metabolomics-annotation/metabolomics_annotation.py --demo --output /tmp/anno_demo

# Real feature table (annotates against demo HMDB dictionary regardless of --database)
python skills/metabolomics/metabolomics-annotation/metabolomics_annotation.py \
  --input features.csv --output results/ \
  --database hmdb --ppm 5.0
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — m/z-match formula, demo-DB caveats
- `references/output_contract.md` — `tables/annotations.csv` schema
- Adjacent skills: `metabolomics-xcms-preprocessing` (upstream — feature × sample matrix), `metabolomics-peak-detection` (upstream — per-sample peak picking), `metabolomics-quantification` (parallel — impute + normalise), `metabolomics-pathway-enrichment` (downstream — pathway analysis on annotated features)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
