---
name: genomics-phasing
description: Load when summarising a phased VCF (output of WhatsHap / SHAPEIT5 / Eagle2) — phased fraction of het variants, phase-block N50, PS-field parsing, pipe-delimited genotype detection. Skip when the input is unphased (run a phaser first) or when calling small variants (use `genomics-variant-calling`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- genomics
- phasing
- haplotype
- whatshap
- shapeit
- eagle
- ps
requires:
- pandas
- numpy
---

# genomics-phasing

## When to use

The user has a phased VCF (from WhatsHap, SHAPEIT5, Eagle2, etc.)
and wants phasing QC: total het count, phased fraction, phase-block
count, phase-block N50 (in bp), per-block sizes. Phasing detection
relies on the `PS` (Phase Set) FORMAT field plus pipe-delimited
genotype encoding (`0|1` vs `0/1`).

This skill does NOT phase variants — it summarises a VCF that has
already been phased.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Phased VCF | `.vcf` with `FORMAT/PS` and pipe-delimited GT | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Per-variant table | `tables/phased_variants.csv` | CHROM/POS/GT/PS/phased flag |
| Phase blocks | `tables/phase_blocks.csv` | per-PS block start/end/length/n_variants |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load VCF (`--input <phased.vcf>`) or generate a demo phased VCF at `output_dir/demo_phased.vcf` with `--n-variants` records (`genomics_phasing.py:200`).
2. Parse records; classify each het as phased (`|` in GT and `PS` populated) or unphased (`/`).
3. Group phased variants by `PS`; compute per-block start / end / length / variant count.
4. Compute phase-block N50 (bp); phased fraction across all hets.
5. Write `tables/phased_variants.csv` (`genomics_phasing.py:327`) + `tables/phase_blocks.csv` (`:345`) + `report.md` + `result.json` (`:348`).

## Gotchas

- **No phaser is invoked.** This skill ingests an already-phased VCF — it does not run WhatsHap / SHAPEIT5 / Eagle2. Run a phaser upstream and feed its VCF here.
- **`--input` REQUIRED unless `--demo`.** `genomics_phasing.py:314` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError` at `:317`.
- **Unphased VCFs produce empty phase-block tables.** A VCF without any `|` genotypes or `PS` fields will report `phased_fraction = 0` and an empty `phase_blocks.csv` — but the run does NOT fail. Always check the summary before drawing conclusions.
- **`PS` is required for block grouping — without it you get ZERO blocks.** When `PS` is absent, `genomics_phasing.py:126` falls back to `str(pos)` so every variant becomes a singleton phase-set; then `:157` filters out blocks with `< 2` variants, producing zero phase blocks and `phase_block_n50_bp = 0`. WhatsHap output always includes `PS`; some other phasers do not — verify before interpreting an "unphased" report.
- **Multi-sample VCFs are NOT supported.** Only the first sample column is parsed; multi-sample phasing comparison is out of scope.
- **Demo VCF synthesises ~80% phased het variants in 5–20 blocks.** Useful for orchestrator smoke tests; not biologically meaningful.

## Key CLI

```bash
# Demo (2000 synthetic phased variants)
python omicsclaw.py run genomics-phasing --demo --output /tmp/phase_demo

# Real WhatsHap-phased VCF
python omicsclaw.py run genomics-phasing \
  --input sample.whatshap.vcf --output results/
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — PS-field semantics, phase-block N50 definition
- `references/output_contract.md` — `tables/phased_variants.csv` + `phase_blocks.csv`
- Adjacent skills: `genomics-variant-calling` (upstream — produces VCF that gets phased), `genomics-vcf-operations` (parallel — VCF stats / filtering on the same input), `genomics-variant-annotation` (downstream — annotate phased variants with gene context)
