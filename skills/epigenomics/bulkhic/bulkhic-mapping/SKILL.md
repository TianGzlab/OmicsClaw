---
name: bulkhic-mapping
description: "Load when mapping bulk Hi-C reads to ligation-junction pairs: bwa-mem2 mem -SP5M (mates mapped independently) then pairtools parse/sort/dedup into a pairix-indexed .pairs.gz, with 4DN library-QC metrics (valid-pair, duplicate, cis fraction, cis-trans ratio). Builds the reference if not supplied. Skip for ATAC/ChIP; next step is bulkhic-matrix."
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
  - epigenomics
  - hi-c
  - 3c
  - mapping
  - bwa-mem2
  - pairtools
  - pairs
requires:
  - pandas
---

> **Status: implemented** (bwa-mem2 + pairtools). Step 2 of the bulk Hi-C suite.

## When to use

The user has trimmed Hi-C FASTQs from `bulkhic-preprocessing` and wants the 4DN
upstream: map each mate, extract ligation junctions, deduplicate, and produce a
QC'd `.pairs` file. Skip for ATAC/ChIP. The next step (`bulkhic-matrix`) turns
the pairs into a balanced contact matrix.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-1 result | `<project>/preprocessing/result.json` (`sample_sheet` + `preprocessing[]`) | Yes (via `--prev-result`, or sibling-detected from `--wd`) |
| Reference | FASTA + bwa-mem2 index (+ chrom.sizes) | Auto-built in `--ref-dir`; supply `--bwa-mem2-index`/`--bwa-index` to skip |

| Output | Path | Notes |
|---|---|---|
| Pairs | `<output>/pairs/<sample>/<sample>.nodups.pairs.gz` (+ `.px2`) | deduplicated, pairix-indexed |
| Summary | `<output>/mapping_summary.csv` | per-sample pairtools QC |
| Result envelope | `<output>/result.json` | `mapping[]` (pairs + QC) + `genome_files` (chrom_sizes) + `sample_sheet` for bulkhic-matrix |

## Flow

1. Load Step-1 result → trimmed FASTQ paths + genome.
2. Resolve reference: reuse a local `reference_<genome>/<genome>.fa` or download FASTA, build the bwa-mem2 index, and derive **chrom.sizes** offline via `samtools faidx`.
3. Per sample: `bwa-mem2 mem -SP5M | pairtools parse --min-mapq 30 --walks-policy 5unique | pairtools sort` → `pairtools dedup` → pairix; parse the dedup stats into the 4DN QC metrics.
4. Write `report.md`, `result.json`, `reproducibility/`, `README.md`.

## Gotchas

- **`-SP5M` matters.** The two mates are mapped *independently* — Hi-C molecules are chimeric, so standard PE mate-rescue/pairing would create false contacts.
- **chrom.sizes is required downstream** (cooler/cooltools). It is derived locally from the FASTA `.fai`, so no UCSC chrom.sizes download is needed.
- **No control concept** — Hi-C has no input library.
- **QC tiers are guidance, not gates** — Hi-C quality is depth/protocol-dependent (see `bulkhic_qc_criteria`).

## Key CLI

```bash
python skills/epigenomics/bulkhic/bulkhic-mapping/bulkhic-mapping.py \
    --prev-result ./hic_run/preprocessing/result.json --wd ./hic_run/mapping --threads 32
```

## See also

- `references/methodology.md` — `-SP5M` rationale, pairtools pipeline, QC metrics.
- Upstream — `bulkhic-preprocessing`. Downstream — `bulkhic-matrix`.
- Parallel — `bulkatac-mapping`, `bulkchip-mapping` (BAM-based; Hi-C is pairs-based).
