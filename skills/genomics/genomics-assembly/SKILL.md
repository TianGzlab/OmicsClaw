---
name: genomics-assembly
description: Load when computing genome-assembly QC metrics — N50/N90, L50/L90, total length, contig count, GC content, longest-contig — from a FASTA produced by any assembler (SPAdes / Megahit / Flye / Canu). Skip when running the assembly itself or when assessing alignment quality (use `genomics-alignment`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- genomics
- assembly
- n50
- l50
- contig
- quast
- spades
- flye
requires:
- pandas
- numpy
---

# genomics-assembly

## When to use

The user has a FASTA from any de novo assembler (SPAdes, Megahit,
Flye, Canu, etc.) and wants standard QUAST-compatible quality
metrics: contig count, N50 / N90, L50 / L90, total length, longest
contig, GC content, optional completeness fraction (when
`--genome-size` is provided).

This skill does NOT run the assembly. It consumes the FASTA the
assembler emits.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Assembled contigs | `.fasta` / `.fa` | yes (unless `--demo`) |
| Expected genome size | `--genome-size <bp>` (used for completeness %) | optional |

| Output | Path | Notes |
|---|---|---|
| Per-contig table | `tables/contig_lengths.csv` | one row per contig with `contig` + `length` (no GC column — GC is assembly-wide only) |
| Assembly metrics | `tables/assembly_metrics.csv` | one-row N50/L50/total/longest summary |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load FASTA (`--input <assembly.fasta>`) or generate a demo assembly at `output_dir/demo_assembly.fasta` (`genome_assembly.py:186`).
2. Parse contigs (`genome_assembly.py:52-67`); each line is uppercased on read so case is normalised.
3. Sort by length; compute cumulative N50 / N90 / L50 / L90 + total / longest + assembly-wide GC% from concatenated sequence.
4. If `--genome-size` is set and > 0, compute `completeness_pct = total_length / genome_size * 100`.
5. Write `tables/contig_lengths.csv` (`genome_assembly.py:309`) + `tables/assembly_metrics.csv` (`:312`) + `report.md` + `result.json`.

## Gotchas

- **No assembler is invoked.** This skill summarises an existing FASTA — it does not run SPAdes / Megahit / Flye / Canu. Run them upstream and feed the resulting FASTA here.
- **`--input` REQUIRED unless `--demo`.** `genome_assembly.py:290` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError` at `:293`.
- **`--genome-size 0` (default) skips completeness.** Without an expected genome size (`genome_assembly.py:279`, default 0), the report omits the completeness column entirely. Pass `--genome-size 3000000000` for a human-scale assembly to populate it.
- **Soft-masked bases are normalised to uppercase before GC counting.** `genome_assembly.py:67` calls `line.upper()` per FASTA line, so lowercase soft-masked regions contribute identically to hard-masked / unmasked sequence in the GC%. There is no way to exclude soft-masked regions short of pre-filtering the FASTA.
- **Demo FASTA has 100 contigs of varying length.** `--demo` writes a fixed-pattern synthetic file useful for orchestrator smoke tests; the N50 it produces is not biologically meaningful.

## Key CLI

```bash
# Demo
python omicsclaw.py run genomics-assembly --demo --output /tmp/asm_demo

# Real assembly with completeness against expected size
python omicsclaw.py run genomics-assembly \
  --input my_assembly.fasta --output results/ \
  --genome-size 3100000000
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — N50 / L50 definitions, GC interpretation
- `references/output_contract.md` — `tables/assembly_metrics.csv` schema
- Adjacent skills: `genomics-alignment` (downstream — map reads back to your assembly to validate), `genomics-qc` (upstream — FASTQ QC before assembly), `genomics-cnv-calling` (parallel — copy-number on a known reference instead of de novo)
