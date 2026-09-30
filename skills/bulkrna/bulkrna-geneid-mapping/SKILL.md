---
name: bulkrna-geneid-mapping
description: Load when converting gene identifiers between Ensembl, Entrez, and HGNC symbol in a bulk
  RNA-seq count matrix. Skip when the input is already in the desired identifier system; organisms outside
  human/mouse; non-bulk-counts inputs.
trigger: gene ID, Ensembl, Entrez, gene symbol, ID mapping, gene annotation, convert IDs
tags:
- bulkrna
- gene-id
- mapping
- Ensembl
- Entrez
- HGNC
- annotation
---

# bulkrna-geneid-mapping

## When to use

Run between counting and downstream analysis when the gene identifiers
in your count matrix don't match the namespace of your downstream tool
(e.g. STARsolo gives Ensembl IDs but GSEA wants HGNC symbols).
Currently supports Ensembl ↔ Entrez ↔ HGNC symbol for human and mouse
via built-in tables, with optional mygene API enrichment.  UniProt is
not supported — feed via `--mapping-file` if needed.

## Inputs & Outputs

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/mapped_counts.csv`
- `tables/mapping_table.csv`
- `tables/unmapped_genes.csv`
- `report.md`
- `result.json`
- Produces artifact `bulkrna.count_matrix` as `tables/mapped_counts.csv` (`csv`)

## Flow

1. Load count matrix.
2. Strip Ensembl version suffixes (`bulkrna_geneid_mapping.py`: `ENSG00000141510.12 → ENSG00000141510`).
3. Look up each ID in the built-in mapping table; fall back to the mygene API if available (`_try_mygene_mapping` warns and skips API path if `mygene` not importable).
4. Resolve duplicate-target collisions per `--on-duplicate` (`sum` / `first` / `drop`).
5. Write `tables/mapped_counts.csv`, `tables/mapping_table.csv`, `tables/unmapped_genes.csv`.

## Gotchas

- **mygene API is opt-in via package install, not a CLI flag.**  `bulkrna_geneid_mapping.py` falls back silently when `mygene` is not importable, leaving you with built-in-table coverage only.  The summary dict does not record whether the API was used; the only signal is the warning log line and the `pct_mapped` value (built-in tables cover ~20 well-known cancer-relevant genes — anything substantially higher implies the API ran).
- **`--from`/`--to` only accept `ensembl`, `entrez`, `symbol`** (`bulkrna_geneid_mapping.py`).  UniProt and other namespaces are not in the choices list and will fail at argparse.  If you need UniProt, supply a custom `--mapping-file` TSV.
- **Built-in tables cover human + mouse only** (`--species` choices).  Other organisms fail with empty mappings if `mygene` isn't installed; either install `mygene` or supply `--mapping-file`.
- **Many-to-one collapses follow `--on-duplicate` (default `sum`).**  Default sums read counts across genes mapping to the same target symbol — meaningful for paralog families but wrong if you wanted per-isoform tracking.  Choose `first` to take the first hit, or `drop` to keep only unique mappings.  The number resolved is in `result.json["n_duplicates_resolved"]`.
- **Ensembl version stripping is unconditional**.  If your downstream tool *requires* the version suffix (rare), this skill silently drops it.

## Key CLI

```bash
python skills/bulkrna/bulkrna-geneid-mapping/bulkrna_geneid_mapping.py --demo --output /tmp/bulkrna-geneid-mapping_demo
python skills/bulkrna/bulkrna-geneid-mapping/bulkrna_geneid_mapping.py \
  --input counts.csv --output results/ \
  --from ensembl --to symbol --species human
python skills/bulkrna/bulkrna-geneid-mapping/bulkrna_geneid_mapping.py \
  --input counts.csv --output results/ \
  --from ensembl --to symbol --on-duplicate first
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — built-in tables, mygene fallback, version-suffix stripping
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-qc` (run before to inspect raw IDs), `bulkrna-de` (downstream — DE expects whatever ID system the rest of your pipeline uses), `bulkrna-enrichment` (downstream — enrichment requires HGNC symbols or Entrez IDs in most cases)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`mygene`, `numpy`, `pandas`
