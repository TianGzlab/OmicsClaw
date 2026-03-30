# ChIP-Atlas Target Genes Data Format

## URL Pattern

Pre-computed target gene data is available at:

```
https://chip-atlas.dbcls.jp/data/{genome}/target/{Protein}.{Distance}.tsv
```

| Parameter | Values | Description |
|-----------|--------|-------------|
| `genome` | hg38, hg19, mm10, mm9, rn6, dm6, dm3, ce11, ce10, sacCer3 | Genome assembly |
| `Protein` | e.g., TP53, CTCF, MYC | Transcription factor / protein name (case-sensitive) |
| `Distance` | 1, 5, 10 | Distance from TSS in kilobases (±1kb, ±5kb, ±10kb) |

**Example:** `https://chip-atlas.dbcls.jp/data/hg38/target/TP53.5.tsv`

## TSV File Structure (Wide Format)

| Column Position | Header Format | Description |
|----------------|---------------|-------------|
| 1 | `Target_genes` | Gene symbol (one row per target gene) |
| 2 | `{Protein}\|Average` | Mean MACS2 binding score across all experiments |
| 3..N-1 | `{SRX_ID}\|{Cell_Type}` | Per-experiment MACS2 binding scores |
| N (last) | `STRING` | STRING database interaction score |

**Example header:**
```
Target_genes	TP53|Average	SRX21888064|22Rv1	SRX21888065|22Rv1	...	STRING
```

**Key properties:**
- Rows are pre-sorted by Average column (descending) — top targets first
- Values are MACS2 binding scores (0 = no binding, higher = stronger)
- When multiple peaks overlap one gene, highest score is retained
- Column count varies by antigen (TP53 has ~395 columns; others may have <10)
- Row count varies (TP53: ~16K genes; smaller TFs may have <1K)

## Validating Antigen Availability

**HTTP HEAD check:**
```
HEAD https://chip-atlas.dbcls.jp/data/{genome}/target/{Protein}.{Distance}.tsv
```
- **200:** Data available
- **404:** Antigen not found (check case, or protein may not have ChIP-seq data)

**Notes:**
- ~1,753 unique antigens available for hg38 (as of 2025)
- Only non-histone antigens ("TFs and others") — histone marks (H3K4me3 etc.) return 404
- Protein names are case-sensitive (e.g., `TP53` not `tp53`)

## Related Files on Server

Each antigen has multiple files:
- `{Protein}.{1,5,10}.tsv` — Target gene data at different distance windows
- `STRING_{Protein}.{1,5,10}.tsv` — STRING-enhanced predictions (separate file)
- `{SRX_ID}.{1,5,10}.tsv` — Individual experiment-level target genes

## Computation Method

Target genes are identified by overlapping transcription start sites (TSSs) with ChIP-seq peak-call intervals using `bedtools window`. Only protein-coding genes from UCSC refFlat files are included. Gene symbols follow official nomenclature (HGNC for human, MGI for mouse, etc.).


---
