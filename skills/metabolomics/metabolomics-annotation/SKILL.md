---
name: metabolomics-annotation
description: Load when annotating LC-MS features against a built-in 15-metabolite HMDB demo dictionary by m/z within a `--ppm` tolerance — emits a per-feature annotation table. Skip when needing real HMDB / KEGG / LipidMaps / METLIN look-up (this skill is demo-only) or for raw spectra (use `metabolomics-xcms-preprocessing` first).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- metabolomics
- annotation
- hmdb
- demo
- mz-match
requires:
- pandas
- numpy
---

# metabolomics-annotation

## When to use

The user has a feature table with `mz` (m/z) values and wants
each feature annotated by m/z match to a metabolite database.
**This is demo-only annotation.** The reference is an 15-entry
HMDB dictionary (`metabolomics_annotation.py:57-74`: Glucose,
Lactic acid, Alanine, Glycine, Serine, Proline, Valine, Leucine).
`--database {hmdb,kegg,lipidmaps,metlin}` is recorded as metadata
but does NOT switch the lookup table.

For real database-scale annotation use SIRIUS / GNPS / MetFrag
externally and feed the resulting annotation CSV into a downstream
skill.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Feature table | `.csv` with `mz` column (m/z values) | yes (unless `--demo`) |
| Database | `--database {hmdb,kegg,lipidmaps,metlin}` (default `hmdb`, RECORDED ONLY — does not switch lookup) | no |
| Mass tolerance | `--ppm <float>` (default 10.0) | no |

| Output | Path | Notes |
|---|---|---|
| Annotations | `tables/annotations.csv` | per-feature match (mz → name + HMDB id + formula) |
| Report | `report.md` + `result.json` | `n_annotated`, `database` (recorded value) |

## Flow

1. Load CSV (`--input <features.csv>`) or generate a demo (`--demo`).
2. For each input `mz`, search the 15-entry HMDB dictionary (`metabolomics_annotation.py:57-74`) within `--ppm` tolerance.
3. Write `tables/annotations.csv` (`metabolomics_annotation.py:279`) + `report.md` + `result.json`.

## Gotchas

- **Database is HARD-CODED 8 metabolites — `--database` is metadata only.** `metabolomics_annotation.py:57-74` defines an 15-entry HMDB tuple. The CLI accepts `hmdb` / `kegg` / `lipidmaps` / `metlin` (`:251` choices=...) but the value is only logged into `result.json` — the lookup always uses the same 15-entry HMDB list. For real annotation, use SIRIUS / GNPS / MetFrag externally.
- **`--ppm 10.0` default is m/z-tolerance.** Suitable for high-resolution Orbitrap; for low-resolution Q-TOF use `--ppm 30.0`. The mass-error formula is `|mz_obs - mz_ref| < (ppm × mz_ref / 1e6)`.
- **`--input` REQUIRED unless `--demo`.** `metabolomics_annotation.py:269` raises `ValueError("--input required when not using --demo")`.
- **Required CSV column is `mz`** (lowercase). XCMS exports `mzmed`, MZmine exports `m/z`; rename to `mz` first.
- **Multiple matches per feature ⇒ multiple rows.** A feature with 3 candidate matches yields 3 rows in `tables/annotations.csv`; deduplicate downstream by `feature_id` if you need 1:1.

## Key CLI

```bash
# Demo
python omicsclaw.py run metabolomics-annotation --demo --output /tmp/anno_demo

# Real feature table (annotates against demo HMDB dictionary regardless of --database)
python omicsclaw.py run metabolomics-annotation \
  --input features.csv --output results/ \
  --database hmdb --ppm 5.0
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — m/z-match formula, demo-DB caveats
- `references/output_contract.md` — `tables/annotations.csv` schema
- Adjacent skills: `metabolomics-xcms-preprocessing` (upstream — feature × sample matrix), `metabolomics-peak-detection` (upstream — per-sample peak picking), `metabolomics-quantification` (parallel — impute + normalise), `metabolomics-pathway-enrichment` (downstream — pathway analysis on annotated features)
