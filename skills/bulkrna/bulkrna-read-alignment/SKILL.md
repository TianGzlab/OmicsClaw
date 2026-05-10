---
name: bulkrna-read-alignment
description: Load when summarising STAR / HISAT2 / Salmon alignment-rate logs in bulk RNA-seq. Skip if data is raw FASTQ (use bulkrna-read-qc) or already counted (use bulkrna-qc), or for genome-DNA alignment (use genomics-alignment).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- alignment
- STAR
- HISAT2
- Salmon
- mapping-rate
- strandedness
requires:
- numpy
- pandas
- matplotlib
---

# bulkrna-read-alignment

## When to use

Run after the aligner / quantifier finishes, on the log file produced by
STAR (`Log.final.out`), HISAT2 (`.log`), or Salmon (`meta_info.json`).
Yields a one-page mapping-rate summary, strandedness inference, and a
gene-body coverage profile — the QC bridge between raw FASTQ and the
count matrix.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Aligner log | `Log.final.out` (STAR), `.log` (HISAT2), `meta_info.json` (Salmon) | yes (or `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Mapping summary figure | `figures/mapping_summary.png` | unique vs multi vs unmapped |
| Gene body coverage | `figures/gene_body_coverage.png` | 5'→3' bias profile |
| Alignment composition | `figures/alignment_composition.png` | breakdown of mapping outcomes |
| Stats table | `tables/alignment_stats.csv` | parsed numeric metrics |
| Report | `report.md` + `result.json` | always |

## Flow

1. Auto-detect aligner from filename (`bulkrna_read_alignment.py:305-311`): `log.final.out` → STAR; `meta_info` → Salmon; otherwise → HISAT2.
2. Parse the log into a numeric stats dict.
3. Run quality assessment heuristics (high/medium/low mapping-rate buckets).
4. Render figures and write `report.md` + `tables/alignment_stats.csv`.

## Gotchas

- **Aligner detection is filename-based, not content-based.**  `bulkrna_read_alignment.py:305-311` dispatches by `input_path.name.lower()` — anything that is neither `log.final.out` nor `meta_info` (case-insensitive substring) is silently parsed as a HISAT2 log.  A renamed STAR log will produce nonsense.  Pass `--method star` explicitly if your STAR file isn't named conventionally.
- **The skill consumes the LOG, not the BAM.**  Feeding a `.bam` or `.sam` file as `--input` will not raise — the parser just finds zero matchable lines and reports an empty stats dict.  Sanity-check `result.json["stats"]["total_reads"]` is non-zero before trusting any downstream summary.
- **Gene body coverage is synthetic in `--demo` mode** (`bulkrna_read_alignment.py:142-150`).  The 5'→3' bias profile in demo runs is a fixed reproducible curve, not derived from real input — useful for layout previews but not for assessing real RNA degradation.

## Key CLI

```bash
python omicsclaw.py run bulkrna-read-alignment --demo
python omicsclaw.py run bulkrna-read-alignment --input Log.final.out --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — STAR / HISAT2 / Salmon parsers, strandedness inference
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-read-qc` (upstream FASTQ QC), `bulkrna-qc` (downstream count-matrix QC), `genomics-alignment` (DNA-alignment sibling: BAM/SAM, not log files)
