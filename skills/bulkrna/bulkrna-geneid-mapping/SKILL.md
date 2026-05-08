---
name: bulkrna-geneid-mapping
description: >-
  Gene identifier conversion between Ensembl, Entrez, HGNC symbols, and UniProt for
  bulk RNA-seq count matrices.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, gene-id, mapping, Ensembl, Entrez, HGNC, annotation]
requires: [numpy, pandas]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🏷️"
    trigger_keywords: [gene ID, Ensembl, Entrez, gene symbol, ID mapping, gene annotation,
      convert IDs]
    allowed_extra_flags:
    - "--from"
    - "--mapping-file"
    - "--on-duplicate"
    - "--species"
    - "--to"
    legacy_aliases: [bulk-geneid]
    saves_h5ad: false
    script: bulkrna_geneid_mapping.py
    param_hints: {}
    requires_preprocessed: false
---

# Bulk RNA-seq Gene ID Mapping

Convert gene identifiers in bulk RNA-seq count matrices between major ID systems: Ensembl Gene IDs, Entrez Gene IDs, HGNC Symbols, and UniProt accessions. Features built-in mapping tables with optional `mygene` API fallback.

## Core Capabilities

- Convert between Ensembl, Entrez, HGNC symbol, and UniProt identifiers
- Strip Ensembl version suffixes (ENSG00000141510.12 → ENSG00000141510)
- Handle duplicate gene symbols by summing counts (standard practice)
- Built-in mapping for human (GRCh38) and mouse (GRCm39); extensible via mygene API
- Report unmapped genes with fallback strategies
- Apply mapping directly to count matrices

## Why This Exists

- **Without it**: Researchers manually download BioMart tables, write custom scripts to handle version suffixes, resolve duplicates, and cross-reference multiple ID systems.
- **With it**: A single command converts the entire count matrix index to the desired ID system with proper duplicate handling and unmapped gene reporting.
- **Why OmicsClaw**: Integrated into the bulkrna pipeline so IDs are harmonized before DE analysis, enrichment, or cross-study comparison.

## Algorithm / Methodology

### ID Resolution Pipeline
1. Strip version suffixes from Ensembl IDs (if applicable)
2. Apply primary mapping from built-in tables or mygene API query
3. Handle unmapped genes: keep original ID, drop, or mark as unmapped
4. Resolve duplicate target IDs by summing read counts per gene

### Supported ID Types

| Type | Example | Common Use |
|------|---------|-----------|
| Ensembl Gene | ENSG00000141510 | RNA-seq quantification, GTF annotation |
| Entrez Gene | 7157 | NCBI databases, KEGG pathways |
| HGNC Symbol | TP53 | Human-readable, publications |
| UniProt | P04637 | Protein databases |

## Input Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Count matrix | `.csv` | Genes as rows (any ID type), samples as columns |
| Mapping table | `.tsv` | Optional custom mapping: `from_id`, `to_id` columns |

## CLI Reference

```bash
python omicsclaw.py run bulkrna-geneid-mapping --demo
python omicsclaw.py run bulkrna-geneid-mapping --input counts.csv --from ensembl --to symbol --output results/
python bulkrna_geneid_mapping.py --demo --output /tmp/geneid_demo
```

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── tables/
│   ├── mapped_counts.csv
│   ├── mapping_table.csv
│   └── unmapped_genes.csv
└── reproducibility/
    └── commands.sh
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | — | Path to count matrix CSV |
| `--from` | `ensembl` | Source ID type: `ensembl`, `entrez`, `symbol` |
| `--to` | `symbol` | Target ID type: `ensembl`, `entrez`, `symbol` |
| `--species` | `human` | Species: `human` or `mouse` |
| `--mapping-file` | — | Optional custom mapping TSV |
| `--on-duplicate` | `sum` | Duplicate handling: `sum`, `first`, `drop` |

## Safety

- **Local-first**: All processing runs locally; mygene API is optional fallback.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.

## Integration with Orchestrator

**Chaining partners**:
- `bulkrna-qc` — Upstream: count matrix QC
- `bulkrna-de` — Downstream: DE analysis with harmonized IDs
- `bulkrna-enrichment` — Downstream: pathway enrichment requires specific ID types

## Dependencies

**Required**: numpy, pandas
**Optional**: mygene (for API-based mapping when built-in tables insufficient)

## Related Skills

- `bulkrna-qc` — Count matrix QC upstream
- `bulkrna-de` — Differential expression downstream
- `bulkrna-enrichment` — Pathway enrichment (often requires Entrez IDs)
