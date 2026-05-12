---
name: proteomics-structural
description: Load when summarising cross-linking MS (XL-MS) results — intra/inter-protein link split, optional FDR filtering, distance-constraint validation against a per-crosslinker (DSS / BS3 / EDC / DSSO / DSBU) max distance. Skip when raw spectra are the input (run XlinkX / pLink / xiSEARCH first) or no XL-MS experiment was performed.
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- proteomics
- structural
- xl-ms
- crosslinking
- dss
- bs3
- dsso
- dsbu
- edc
requires:
- pandas
- numpy
---

# proteomics-structural

## When to use

The user has a cross-linking MS (XL-MS) results CSV (from XlinkX,
pLink, xiSEARCH, etc.) and wants a summary: intra- vs inter-protein
classification, optional FDR filtering, and distance-constraint
validation against the per-crosslinker max distance (Rappsilber
(2011) Cα-Cα bounds).

`--crosslinker {DSS,BS3,EDC,DSSO,DSBU}` (default `DSS`) sets the
max-distance threshold (`CROSSLINKER_CONSTRAINTS` at
`struct_proteomics.py:43-49`: DSS/BS3/DSSO/DSBU = 30 Å, EDC =
20 Å). `--fdr` (default 0.05) filters by the `fdr` column when
present.

This skill does NOT run an XL-MS search engine — feed it the
already-searched results.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Cross-link results | `.csv` with `protein_a`, `protein_b` columns (lowercase, used to derive `link_type`); optional `fdr` (for filtering), `distance_angstrom` (for constraint check), `score` | yes (unless `--demo`) |
| Crosslinker | `--crosslinker {DSS,BS3,EDC,DSSO,DSBU}` (default `DSS`) | no |
| FDR | `--fdr <float>` (default 0.05) | no |

| Output | Path | Notes |
|---|---|---|
| All crosslinks | `tables/crosslinks.csv` | FDR-filtered subset; adds derived `link_type` and (if distances present) `constraint_satisfied` columns |
| Inter-protein subset | `tables/inter_protein_crosslinks.csv` | only when ≥ 1 row has `link_type == "inter-protein"` |
| Report | `report.md` + `result.json` | `n_crosslinks`, `n_inter`, `n_intra`, distance statistics, `constraint_satisfaction_rate` (if `distance_angstrom` present) |

## Flow

1. Load CSV (`--input <crosslinks.csv>`) or generate a demo at `output_dir/demo_crosslinks.csv` (`struct_proteomics.py:102`).
2. If `fdr` column present, filter to `df[df["fdr"] <= --fdr]` (`struct_proteomics.py:126`); otherwise pass-through (`:130`).
3. Derive `link_type` from `protein_a == protein_b` comparison when both columns are present (`struct_proteomics.py:134-141`); otherwise count all rows as intra (`:142-145`).
4. If `distance_angstrom` column present, compute satisfaction rate vs `CROSSLINKER_CONSTRAINTS[--crosslinker]` (`struct_proteomics.py:147-167`); add per-row `constraint_satisfied` boolean column.
5. Write `tables/crosslinks.csv` (`struct_proteomics.py:282`) + `tables/inter_protein_crosslinks.csv` (only if non-empty, `:287`) + `report.md` + `result.json` (`:290`).

## Gotchas

- **Required input columns are `protein_a` and `protein_b`** (lowercase, with underscore-letter — NOT `protein1` / `protein2`). `struct_proteomics.py:134` checks `{"protein_a", "protein_b"}.issubset(df_filtered.columns)`. Without both, ALL rows silently classify as `intra-protein` (`:142-145`) — n_inter = 0 even on a real inter-protein dataset. XlinkX exports use `Protein A` / `Protein B`; rename first.
- **`--crosslinker` drives the distance-constraint check, NOT just metadata.** `struct_proteomics.py:148` sets `max_distance = CROSSLINKER_CONSTRAINTS.get(crosslinker.upper(), 30.0)` — the active threshold for `constraint_satisfied` column + `constraint_satisfaction_rate` summary. Choices: DSS / BS3 / DSSO / DSBU = 30 Å, EDC = 20 Å (Rappsilber 2011 Cα-Cα bounds).
- **Distance check is OPT-IN by `distance_angstrom` column presence.** Without that column, `constraint_satisfaction_rate` defaults to 100% (`struct_proteomics.py:170`) — the constraint feature is silently skipped, not failed. Pass `distance_angstrom` (Cα-Cα predicted distance from a 3D model) for a real check.
- **`fdr` filter is OPT-IN by column presence.** `struct_proteomics.py:126` only filters when `fdr` exists — without that column, EVERY input row is kept regardless of `--fdr`. Pre-add an `fdr` column (or a placeholder of zeros) if you need the filter to bite.
- **`--input` REQUIRED unless `--demo`.** `struct_proteomics.py:270` raises `ValueError("--input required when not using --demo")`.
- **`tables/inter_protein_crosslinks.csv` only appears when there ARE inter-protein links.** A purely-intra dataset writes only `tables/crosslinks.csv`. Downstream consumers should check file existence.

## Key CLI

```bash
# Demo
python omicsclaw.py run proteomics-structural --demo --output /tmp/xl_demo

# Real XL-MS data, default DSS / 5% FDR
python omicsclaw.py run proteomics-structural \
  --input crosslinks.csv --output results/

# DSBU at 1% FDR
python omicsclaw.py run proteomics-structural \
  --input crosslinks.csv --output results/ \
  --crosslinker DSBU --fdr 0.01

# EDC (zero-length, 20 Å threshold)
python omicsclaw.py run proteomics-structural \
  --input crosslinks.csv --output results/ \
  --crosslinker EDC --fdr 0.05
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — XL-MS workflow, Rappsilber Cα-Cα bounds, FDR caveats
- `references/output_contract.md` — `tables/crosslinks.csv` schema, derived columns
- Adjacent skills: `proteomics-data-import` (parallel — peptide / protein-level workflows), `proteomics-ptm` (parallel — PTM analysis), `proteomics-quantification` (parallel — protein abundance), `proteomics-enrichment` (downstream — pathway enrichment on inter-protein partners)
