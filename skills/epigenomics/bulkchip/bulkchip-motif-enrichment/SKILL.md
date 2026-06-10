---
name: bulkchip-motif-enrichment
description: "Load when running HOMER motif enrichment on bulk ChIP-seq peaks — known-motif enrichment + de novo discovery on consensus, per-condition, or DA up/down peak subsets. Recovers a TF's own motif or co-bound TFs for histone marks. Skip for bulk ATAC (use bulkatac-motif-enrichment) or before peaks are called."
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- chip-seq
- motif-enrichment
- homer
- findmotifsgenome
- known-motifs
- de-novo-motifs
- transcription-factor
requires:
- pandas
- numpy
---

> **Status: implemented** (HOMER-backed). See `_lib/motif_enrichment.py`.


## When to use

The user has ChIP-seq peaks from `bulkchip-peak-calling` (consensus / per-condition) or differential peaks from `bulkchip-DA` (up/down) and wants HOMER motif enrichment: known-motif over-representation and de novo motif discovery. For a TF ChIP this is the key validation — the ChIP'd factor's own motif should top the list; for histone marks it surfaces co-localized TF motifs. Skip for bulk ATAC (`bulkatac-motif-enrichment`) or before peaks exist.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-3 result | `<project>/peak_calling/result.json` (consensus / per-condition peaks) | Yes (via `--prev-result`, or sibling-detected from `--wd`) |
| DA result | `bulkchip-DA` result.json | Only for `--peak-subset up/down` (via `--de-result`) |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Top known motifs per subset, de novo hits |
| Result envelope | `<output>/result.json` | `motif_enrichment`, chained from upstream |
| Summary | `<output>/motif_enrichment_summary.csv` | Top known motifs (name, p-value, % targets) |
| HOMER output | `<output>/<subset>/` | `knownResults.*`, `homerResults.html` |

## Flow

1. Locate the upstream `result.json`; resolve the requested peak subset (consensus / per-condition / DA up/down).
2. `run_all_motif_enrichment` — HOMER `findMotifsGenome.pl <peaks> <genome> <out> -size <size> -len <len>`.
3. Parse `knownResults.txt` for the top enriched motifs; write summary.
4. Write `report.md`, `result.json`, `reproducibility/`, `README.md`.

## Gotchas

- **`up`/`down` need a DA result.** `--peak-subset up`/`down` requires `--de-result <bulkchip-DA result.json>`; otherwise only `consensus`/`condition` subsets are available from Step 3.
- **HOMER genome must be installed.** `findMotifsGenome.pl` needs the HOMER genome package (e.g. `perl configureHomer.pl -install hg38`) or a FASTA path; the run errors with guidance if absent.
- **`--size 200` centers on summits** (point-source default); use `--size given` to scan full peak intervals (better for broad marks).
- **Interpretation differs by target.** TF ChIP → expect the factor's motif; broad histone marks → co-bound TF motifs, not a single "mark motif".

## Key CLI

```bash
python skills/epigenomics/bulkchip/bulkchip-motif-enrichment/bulkchip-motif-enrichment.py \
    --wd ./chip_run/motif --peak-subset consensus --size 200
```

Motifs in gained peaks from a differential contrast:

```bash
python skills/epigenomics/bulkchip/bulkchip-motif-enrichment/bulkchip-motif-enrichment.py \
    --wd ./chip_run/motif --peak-subset up \
    --de-result ./chip_run/DA/result.json
```

## See also

- `references/parameters.md` — every CLI flag with type + default.
- `references/methodology.md` — HOMER findMotifsGenome.pl parameters, size/len rationale, known vs de novo.
- `references/output_contract.md` — output tree + `motif_enrichment_summary.csv` / `result.json` schemas.
- Adjacent skills:
  - Upstream — `bulkchip-peak-calling` (Step 3); `bulkchip-DA` (Step 4, for up/down subsets).
  - Sibling — `bulkchip-annotation-enrichment` (peak→gene annotation + GO/KEGG).
  - Parallel — `bulkatac-motif-enrichment` (bulk ATAC).
