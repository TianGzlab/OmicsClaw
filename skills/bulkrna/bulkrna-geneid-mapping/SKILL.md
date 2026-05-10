---
name: bulkrna-geneid-mapping
description: Load when converting gene identifiers between Ensembl, Entrez, HGNC symbol, and UniProt in a bulk RNA-seq count matrix. Skip if the input is already in the desired identifier system, or for non-bulk-counts inputs (use the appropriate domain skill).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- gene-id
- mapping
- Ensembl
- Entrez
- HGNC
- annotation
requires:
- numpy
- pandas
---

# bulkrna-geneid-mapping

## When to use

Run between counting and downstream analysis when the gene identifiers
in your count matrix don't match the namespace of your downstream tool
(e.g. STARsolo gives Ensembl IDs but GSEA wants HGNC symbols).
Supports Ensembl ↔ Entrez ↔ HGNC ↔ UniProt for human and mouse via
built-in tables, with optional mygene API enrichment.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Count matrix | `.csv` (gene id col + sample count cols) | yes (or `--demo`) |
| Custom mapping | `--mapping-file` TSV | optional, overrides built-ins |

| Output | Path | Notes |
|---|---|---|
| Mapped matrix | `tables/counts_mapped.csv` | same shape, gene column rewritten |
| Unmapped IDs | `tables/unmapped.csv` | original IDs that couldn't be resolved |
| Mapping audit | `result.json["mapping_stats"]` | mapped / unmapped / collapsed counts |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load count matrix.
2. Strip Ensembl version suffixes (`bulkrna_geneid_mapping.py:78`: `ENSG00000141510.12 → ENSG00000141510`).
3. Look up each ID in the built-in mapping table; fall back to the mygene API if available (`:88` warns and skips API path if `mygene` not importable).
4. Resolve duplicate-target collisions per `--on-duplicate` (`sum` / `first` / `drop`).
5. Write `tables/counts_mapped.csv` + unmapped audit.

## Gotchas

- **mygene API is opt-in via package install, not a CLI flag.**  `bulkrna_geneid_mapping.py:88` falls back silently when `mygene` is not importable, leaving you with built-in-table coverage only.  `result.json["mapping_stats"]["api_used"]` is the source of truth — check it before reporting low mapping rates as a biology problem.
- **Built-in tables cover human + mouse only** (`--species` choices at `:275`).  Other organisms fail with empty `tables/counts_mapped.csv` if `mygene` isn't installed; either install `mygene` or supply `--mapping-file`.
- **Many-to-one collapses are silent unless `--on-duplicate` is set explicitly.**  Default `sum` (`:276`) merges read counts across genes mapping to the same target symbol — meaningful for paralog families but wrong if you wanted per-isoform tracking.  Choose `first` to take the first hit, or `drop` to keep only unique mappings.
- **Ensembl version stripping is unconditional** (`:78`).  If your downstream tool *requires* the version suffix (rare), this skill silently drops it.  Run a no-op identity mapping (`--from ensembl --to ensembl`) only if you specifically want the version-stripping side effect.

## Key CLI

```bash
python omicsclaw.py run bulkrna-geneid-mapping --demo
python omicsclaw.py run bulkrna-geneid-mapping \
  --input counts.csv --output results/ \
  --from ensembl --to symbol --species human
python omicsclaw.py run bulkrna-geneid-mapping \
  --input counts.csv --output results/ \
  --from ensembl --to symbol --on-duplicate first
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — built-in tables, mygene fallback, version-suffix stripping
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-qc` (run before to inspect raw IDs), `bulkrna-de` (downstream — DE expects whatever ID system the rest of your pipeline uses), `bulkrna-enrichment` (downstream — enrichment requires HGNC symbols or Entrez IDs in most cases)
