# Promoter Definitions and TSS Handling

How genes are mapped to promoter regions for ChIP-seq peak overlap analysis.

## API TSS Window (Default)

The ChIP-Atlas API uses `distanceUp` and `distanceDown` parameters to define the TSS window:

- **Default:** 5000bp upstream, 5000bp downstream (10kb total)
- **API handles internally:** Gene-to-region conversion done server-side when `typeA=gene`
- **Ensembl lookup optional:** Only needed to populate `input_regions` for downstream compatibility

## Window Parameters

| Window | distanceUp | distanceDown | Total | Use Case |
|--------|-----------|--------------|-------|----------|
| **API Default** | 5000bp | 5000bp | 10kb | Broad regulatory scan |
| **Standard** | 2000bp | 500bp | 2.5kb | Core promoter + proximal |
| **Narrow** | 500bp | 100bp | 600bp | Core promoter only |
| **Wide** | 10000bp | 10000bp | 20kb | Distal regulatory elements |

## Ensembl Gene Coordinate Lookup

When `input_regions` are needed (for export_all.py compatibility), the batch Ensembl POST endpoint is used:

```python
# Batch lookup: single POST for all genes
POST https://rest.ensembl.org/lookup/symbol/human
Body: {"symbols": ["TP53", "CDKN1A", "BAX"]}
```

### TSS Calculation by Strand

**Forward strand (+):** TSS = gene start coordinate
**Reverse strand (-):** TSS = gene end coordinate

```python
if strand == 1:   # Forward
    promoter = [TSS - distance_up, TSS + distance_down]
else:              # Reverse
    promoter = [TSS - distance_down, TSS + distance_up]
```

## Example: CDKN1A (p21)

```
Gene: CDKN1A
Location: chr6:36,651,929-36,659,083 (GRCh38)
Strand: + (forward)
TSS: 36,651,929

With API defaults (5000up/5000down):
  Region: chr6:36,646,929-36,656,929
```

## Edge Cases

- **Gene at chromosome start:** `promoter_start = max(1, tss - upstream)`
- **Overlapping promoters:** Not merged; each gene independent
- **Multiple transcripts:** Ensembl returns canonical transcript by default

## References

- Ensembl REST API: https://rest.ensembl.org
- FANTOM5 CAGE promoter atlas


---
