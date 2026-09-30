---
name: genomics-sv-detection
description: Load when summarising structural variants from an SV VCF (DEL / DUP / INV / TRA) — BND-notation
  parsing, size classification, per-type counts. Skip when working with small SNVs / indels (use genomics-variant-calling);
  calling SVs from BAM (run Manta / Delly / Sniffles first).
trigger: structural variant, SV, Manta, Delly, Lumpy, Sniffles
tags:
- genomics
- structural-variants
- sv
- manta
- delly
- sniffles
- bnd
---

# genomics-sv-detection

## When to use

The user has an SV VCF (from Manta, Delly, Lumpy, Sniffles, etc.)
and wants per-type counts (DEL / DUP / INV / TRA / INS), size
classification (small 50 bp–1 kb / medium 1 kb–100 kb / large
100 kb–10 Mb / very-large > 10 Mb), and BND breakend resolution.

The script does NOT call SVs from a BAM. Run an external SV
caller first; this skill summarises its VCF output.

## Inputs & Outputs

**Inputs**

- File types: `.vcf`

**Outputs**

- `tables/structural_variants.csv`
- `report.md`
- `result.json`

## Flow

1. Load VCF (`--input <sv.vcf>`) or generate a demo SV VCF at `output_dir/demo_structural_variants.vcf` with `--n-svs` records (`sv_detection.py`).
2. Parse records; read `INFO/SVTYPE` (`sv_detection.py`). Records without `INFO/SVTYPE` (e.g. pure BND `ALT` notation from Manta) classify as `UNKNOWN` — there is NO BND-to-TRA resolution.
3. Compute `abs(SVLEN)` for size classification (`sv_detection.py`); bin into size classes; aggregate per-type counts.
4. Write `tables/structural_variants.csv` (`sv_detection.py`) + `report.md` + `result.json`.

## Gotchas

- **No SV caller is invoked.** This skill ingests an SV VCF — it does NOT run Manta / Delly / Lumpy / Sniffles. To CALL SVs, run an external pipeline first.
- **`--input` REQUIRED unless `--demo`.** `sv_detection.py` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError`.
- **`--n-svs` only affects `--demo`** (`sv_detection.py`, default 100). Silently ignored when `--input` is set.
- **Pure BND records without `INFO/SVTYPE` classify as `UNKNOWN`.** `sv_detection.py` reads only `INFO/SVTYPE`; there is no BND `ALT`-notation parser and no `MATEID` pairing logic. Manta callsets that emit translocations as paired BND records (without an `SVTYPE=TRA` INFO field) will appear as UNKNOWN, not TRA. Pre-process with `bcftools view -i 'INFO/SVTYPE!=""'` or with a Manta-specific BND→TRA resolver upstream.
- **`SVLEN` is stored as absolute value in the CSV.** `sv_detection.py` writes `abs(int(info.get("SVLEN", end - pos)))` — a 1234-bp deletion becomes `1234` in the CSV regardless of the input sign. The original signed `SVLEN` is NOT preserved.
- **Demo VCF mixes DEL / DUP / INV / TRA at fixed proportions.** Useful for smoke tests; not biologically meaningful.

## Key CLI

```bash
# Demo (100 synthetic SVs)
python skills/genomics/genomics-sv-detection/sv_detection.py --demo --output /tmp/sv_demo

# Custom demo size
python skills/genomics/genomics-sv-detection/sv_detection.py --demo --n-svs 500 \
  --output /tmp/sv_demo_large

# Real SV VCF
python skills/genomics/genomics-sv-detection/sv_detection.py \
  --input manta_diploid.vcf --output results/
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — SVTYPE / BND semantics, size-class boundaries
- `references/output_contract.md` — `tables/structural_variants.csv` schema
- Adjacent skills: `genomics-alignment` (upstream — provides BAMs for SV callers), `genomics-variant-calling` (parallel — small SNVs / indels), `genomics-cnv-calling` (parallel — copy-number from depth, complementary to SV callers), `genomics-variant-annotation` (downstream — functional impact of breakpoints)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
