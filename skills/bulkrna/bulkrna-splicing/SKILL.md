---
name: bulkrna-splicing
description: Load when summarising rMATS / SUPPA2 alternative-splicing output and identifying significant differential splicing events. Skip if you only have count-level DE (use bulkrna-de) or for splicing in single-cell or spatial data (currently unsupported).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- splicing
- alternative-splicing
- PSI
- rMATS
- SUPPA2
---

# bulkrna-splicing

## When to use

Run AFTER rMATS or SUPPA2 has produced its splicing-event table — this
skill consumes that output (not raw alignments).  Computes per-event
ΔPSI (delta percent-spliced-in), flags events crossing significance and
ΔPSI thresholds, and groups results by event type (SE / A3SS / A5SS /
MXE / RI).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Splicing event table | `.csv` from rMATS or SUPPA2 (event_id, type, ΔPSI, p-value cols) | yes (or `--demo`) |
| `--dpsi-cutoff` | float | default `0.1` (events with abs ΔPSI ≥ this) |
| `--padj-cutoff` | float | default `0.05` (significance threshold) |

| Output | Path | Notes |
|---|---|---|
| Significant events | `tables/sig_splicing_events.csv` | filtered table |
| ΔPSI distribution | `figures/dpsi_distribution.png` | histogram with cutoff lines |
| Event-type breakdown | `figures/event_type_bar.png` | SE / A3SS / A5SS / MXE / RI counts |
| Volcano | `figures/splicing_volcano.png` | ΔPSI vs -log10(padj) |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load splicing event table.  Hard-fail at `bulkrna_splicing.py:365,368` on missing or invalid `--input`.
2. Detect format (rMATS vs SUPPA2) by column shape.
3. Filter by `--dpsi-cutoff` AND `--padj-cutoff`.
4. Group by event type; render distribution + volcano + bar plots.
5. Emit filtered table + report.

## Gotchas

- **This skill consumes the SPLICING TABLE, not BAM or FASTQ.**  Run rMATS or SUPPA2 upstream and feed their output here.  The wrapper does not perform splicing detection itself — feeding it BAM files raises a parser error or silently produces an empty result.
- **`--dpsi-cutoff` is the ABSOLUTE value of ΔPSI.**  Default `0.1` keeps events with `|ΔPSI| ≥ 0.1`, including both inclusion-up and inclusion-down.  Set to `0` to keep all directionally significant events.
- **Format detection is column-name-based.**  rMATS uses `IncLevelDifference` / `FDR`; SUPPA2 uses `dPSI` / `pval`.  Mixed-format input (e.g. SUPPA2 dPSI columns merged into an rMATS-style table) is not handled — the parser picks one format and silently drops the other's columns.
- **Event-type breakdown depends on the upstream tool's classification.**  rMATS reports SE / A3SS / A5SS / MXE / RI as separate files; SUPPA2 uses an EVENT field.  If you concatenate rMATS files manually, ensure each row's event type is preserved or the breakdown bar chart will under-count.

## Key CLI

```bash
python omicsclaw.py run bulkrna-splicing --demo
python omicsclaw.py run bulkrna-splicing \
  --input rmats_se.csv --output results/
python omicsclaw.py run bulkrna-splicing \
  --input suppa2_events.csv --output results/ \
  --dpsi-cutoff 0.2 --padj-cutoff 0.01
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — rMATS vs SUPPA2 format conventions, event-type taxonomy
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-de` (parallel: gene-level DE, complements exon-level splicing), `bulkrna-enrichment` (downstream: pathway view of splicing-affected genes via gene-symbol mapping)
