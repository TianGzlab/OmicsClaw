# ChIP-Atlas Diff Analysis API Format

## API Endpoint

**Base URL:** `POST https://dtn1.ddbj.nig.ac.jp/wabi/chipatlas/`

Same endpoint as enrichment analysis. The `antigenClass` parameter selects the analysis mode.

## Required POST Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `address` | `""` | Hidden but required (empty string) |
| `format` | `"text"` | Response format (NOT "json" like enrichment) |
| `result` | `"www"` | Hidden but required |
| `genome` | See below | Target genome assembly |
| `antigenClass` | `"diffbind"` or `"dmr"` | Analysis type |
| `cellClass` | `"empty"` | Fixed value for diff analysis |
| `threshold` | `"50"` | Fixed value |
| `typeA` | `"srx"` | Input type for group A |
| `bedAFile` | Newline-separated IDs | Experiment IDs for group A |
| `typeB` | `"srx"` | Input type for group B |
| `bedBFile` | Newline-separated IDs | Experiment IDs for group B |
| `permTime` | `"1"` | Fixed value |
| `title` | String | Analysis title |
| `descriptionA` | String | Group A description |
| `descriptionB` | String | Group B description |

## Valid Genomes

| Organism | Assemblies |
|----------|------------|
| Human | hg38, hg19 |
| Mouse | mm10, mm9 |
| Rat | rn6 |
| Fruit fly | dm6, dm3 |
| Worm | ce11, ce10 |
| Yeast | sacCer3 |

## Analysis Types

| antigenClass | Method | Input Data |
|-------------|--------|------------|
| `diffbind` | edgeR | ChIP-seq, ATAC-seq, DNase-seq |
| `dmr` | metilene | Bisulfite-seq |

## Experiment ID Formats

- **SRA:** SRX, ERX, DRX (e.g., `SRX18419259`)
- **GEO:** GSM (e.g., `GSM6765200`)
- Minimum 2 experiments per group

## Response Format

### Initial Submission (format=text)

```
requestId	wabi_chipatlas_2024-0124-1556-59-199-173766
parameters	null
current-time	2024-01-24 15:56:59
start-time
current-state
```

Parse `requestId` from the first line (tab-separated key-value).

### Status Polling

**URL:** `GET {BASE_URL}{requestId}?info=status`

```
status: running
```
or
```
status: finished
```

### Result Retrieval

**URL:** `GET {BASE_URL}{requestId}?info=result&format=zip`

Returns a ZIP archive. Files are inside a `wabi_result/` subdirectory:

| File | Format | Purpose |
|------|--------|---------|
| `wabi_result.bed` | 8-col TSV | Main results: chrom, start, end, counts_A, counts_B, logFC, pvalue, qvalue |
| `wabi_result.igv.bed` | BED9 + GFF3 | Visualization in IGV (color-coded by direction) |
| `wabi_result.log` | Text | Analysis processing log (contains WABI_ID, sample info) |
| `wabi_result.xml` | XML | IGV session file (loads BigWig tracks + regions) |
| `README.md` | Markdown | Description of downloaded files |

**Note:** The main `.bed` file is NOT standard BED9 — it has 8 columns with statistical data.
See [output_format.md](output_format.md) for detailed column definitions.

## Key Differences from Enrichment API

1. `format` is `"text"` not `"json"` — response must be parsed as text
2. `cellClass` is always `"empty"` — no cell type filtering
3. Both `bedAFile` and `bedBFile` contain experiment IDs (not gene lists)
4. Results are ZIP (not TSV) — requires binary download and extraction
5. Typical runtime is 2-10 minutes (longer than enrichment)
