# ChIP-Atlas API Format

API endpoint, parameters, and response format for the ChIP-Atlas Enrichment Analysis.

## API Endpoint

**URL:** `POST https://dtn1.ddbj.nig.ac.jp/wabi/chipatlas/`

**Model:** Asynchronous job (submit -> poll -> retrieve)

**Website:** https://chip-atlas.org/enrichment_analysis

## Submission Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `address` | str | Yes | Empty string `""` |
| `format` | str | Yes | `"json"` for JSON response |
| `result` | str | Yes | `"www"` |
| `genome` | str | Yes | Genome assembly (see below) |
| `antigenClass` | str | Yes | Experiment type (must be non-empty) |
| `cellClass` | str | Yes | Cell type class (must be non-empty, use "All cell types" for all) |
| `threshold` | int | Yes | MACS2 threshold: 50, 100, 200, or 500 |
| `typeA` | str | Yes | Input type: `"gene"` for gene list, `"bed"` for BED regions |
| `bedAFile` | str | Yes | Newline-separated gene symbols or BED content |
| `typeB` | str | Yes | Comparison: `"refseq"` for RefSeq background |
| `bedBFile` | str | Yes | `"empty"` for refseq comparison |
| `permTime` | int | Yes | Permutation count (1 for standard) |
| `title` | str | Yes | Job title (alphanumeric + underscore) |
| `descriptionA` | str | Yes | Dataset A label |
| `descriptionB` | str | Yes | Dataset B label |
| `distanceUp` | int | Yes | Bases upstream of TSS (default: 5000) |
| `distanceDown` | int | Yes | Bases downstream of TSS (default: 5000) |

## Supported Genomes

| Genome | Species |
|--------|---------|
| hg38, hg19 | *Homo sapiens* |
| mm10, mm9 | *Mus musculus* |
| rn6 | *Rattus norvegicus* |
| dm6, dm3 | *Drosophila melanogaster* |
| ce11, ce10 | *Caenorhabditis elegans* |
| sacCer3 | *Saccharomyces cerevisiae* |

## Valid Antigen Classes

- `"TFs and others"` - Transcription factors and co-factors
- `"Histone"` - Histone modifications (H3K4me3, H3K27ac, etc.)
- `"RNA polymerase"` - RNA Pol II and variants
- `"ATAC-Seq"` - Open chromatin
- `"DNase-seq"` - DNase hypersensitivity
- `"Bisulfite-Seq"` - DNA methylation
- `"Input control"` - Control experiments
- `"Annotation tracks"` - Genomic annotations

## Valid Cell Type Classes (hg38)

`"All cell types"`, `"Adipocyte"`, `"Blood"`, `"Bone"`, `"Breast"`, `"Cardiovascular"`, `"Digestive tract"`, `"Epidermis"`, `"Gonad"`, `"Kidney"`, `"Liver"`, `"Lung"`, `"Muscle"`, `"Neural"`, `"Others"`, `"Pancreas"`, `"Placenta"`, `"Pluripotent stem cell"`, `"Prostate"`, `"Uterus"`

## Job Lifecycle

### 1. Submit Job

```python
response = requests.post(WABI_API_URL, data={...})
request_id = response.json()["requestId"]
```

### 2. Poll Status

```
GET {WABI_API_URL}{request_id}?info=status
```

Returns text with `status: running` or `status: finished`.

### 3. Retrieve Results

```
GET {WABI_API_URL}{request_id}?info=result&format=tsv
```

## TSV Response Format

11 tab-separated columns, no header:

| Column | Name | Type | Example |
|--------|------|------|---------|
| 1 | Experiment ID | str | SRX21147142 |
| 2 | Antigen class | str | TFs and others |
| 3 | Antigen | str | TP53 |
| 4 | Cell type class | str | Blood |
| 5 | Cell type | str | MOLM-13 |
| 6 | Number of peaks | int | 99 |
| 7 | Input overlap | str | 4/5 |
| 8 | Background overlap | str | 10/18851 |
| 9 | log10(P-value) | float | -12.0222 |
| 10 | log10(Q-value) | float | -8.15177 |
| 11 | Fold enrichment | float | 1508.08 |

**Notes:**
- P/Q values of 0 indicate p=1 (non-significant)
- Fold enrichment of 1e-06 indicates depletion (0 overlap in query)
- Results sorted by significance

## References

- Zou et al. (2024). "ChIP-Atlas 3.0." *Nucleic Acids Research*.
- WABI API: https://github.com/inutano/chip-atlas/wiki
