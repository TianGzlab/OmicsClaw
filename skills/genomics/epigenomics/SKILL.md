---
name: epigenomics
description: >-
  Epigenomics analysis including ATAC-seq peak calling with MACS3,
  ChIP-seq analysis, motif enrichment, and chromatin accessibility.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [genomics, epigenomics, ATAC-seq, ChIP-seq, MACS, peaks, motif]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "🧬"
    trigger_keywords: [epigenomics, ATAC-seq, ChIP-seq, peak calling, MACS, motif, chromatin]
---

# 🧬 Epigenomics Analysis

Peak calling and chromatin accessibility analysis for ATAC-seq and ChIP-seq data.

## Core Capabilities

1. **MACS3 peak calling**: ATAC-specific and ChIP-seq peak detection
2. **Motif analysis**: Homer, MEME motif enrichment in open chromatin regions
3. **Quality control**: Fragment size distribution, TSS enrichment, FRiP scores
4. **Differential accessibility**: Condition comparison of chromatin regions
5. **IDR replicate analysis**: Irreproducible Discovery Rate for peak reproducibility

## CLI Reference

```bash
python omicsclaw.py run epigenomics --demo
python omicsclaw.py run epigenomics --input <data.bam> --output <dir>
```

## Algorithm / Methodology

### MACS3 for ATAC-seq

**Goal:** Identify open chromatin regions from ATAC-seq data using ATAC-specific parameters.

**Approach:** Run MACS3 in paired-end mode with Tn5 shift correction, no model building, and duplicate retention.

```bash
macs3 callpeak \
    -t sample.bam \
    -f BAMPE \
    -g hs \
    -n sample \
    --outdir peaks/ \
    -q 0.05 \
    --nomodel \
    --shift -75 \
    --extsize 150 \
    --keep-dup all \
    -B \
    --call-summits
```

### Why These Parameters?

| Parameter | Reason |
|-----------|--------|
| `--nomodel` | ATAC doesn't have control, can't build model |
| `--shift -75` | Centers on Tn5 insertion site |
| `--extsize 150` | Smooths signal around cut sites |
| `--keep-dup all` | Tn5 creates duplicate cuts at accessible sites |
| `-f BAMPE` | Uses actual fragment size from paired-end |

### Call Peaks on NFR Only

```bash
# Filter to nucleosome-free reads (<100bp fragments)
samtools view -h sample.bam | \
    awk 'substr($0,1,1)=="@" || ($9>0 && $9<100) || ($9<0 && $9>-100)' | \
    samtools view -b > nfr.bam

# Call peaks on NFR
macs3 callpeak -t nfr.bam -f BAMPE -g hs -n sample_nfr \
    --nomodel --shift -37 --extsize 75 --keep-dup all -q 0.01
```

### Broad Peaks (Optional)

```bash
macs3 callpeak -t sample.bam -f BAMPE -g hs -n sample_broad \
    --nomodel --shift -75 --extsize 150 --broad --broad-cutoff 0.1
```

### Batch Processing

```bash
#!/bin/bash
GENOME=hs  # hs for human, mm for mouse
OUTDIR=peaks

mkdir -p $OUTDIR

for bam in *.bam; do
    sample=$(basename $bam .bam)
    macs3 callpeak -t $bam -f BAMPE -g $GENOME -n $sample --outdir $OUTDIR \
        --nomodel --shift -75 --extsize 150 --keep-dup all -q 0.05 -B --call-summits
done
```

### IDR for Replicate Consistency

```bash
# Call peaks on each replicate separately
macs3 callpeak -t rep1.bam -f BAMPE -g hs -n rep1 ...
macs3 callpeak -t rep2.bam -f BAMPE -g hs -n rep2 ...

# Run IDR
idr --samples rep1_peaks.narrowPeak rep2_peaks.narrowPeak \
    --input-file-type narrowPeak --output-file idr_peaks.txt --plot

# Filter by IDR threshold
awk '$5 >= 540' idr_peaks.txt > reproducible_peaks.bed
```

### Convert to BigWig

```bash
sort -k1,1 -k2,2n sample_treat_pileup.bdg > sample.sorted.bdg
bedGraphToBigWig sample.sorted.bdg chrom.sizes sample.bw
```

## Output Files

| File | Description |
|------|-------------|
| `_peaks.narrowPeak` | Peak locations (BED-like) |
| `_summits.bed` | Peak summit positions |
| `_peaks.xls` | Peak statistics |
| `_treat_pileup.bdg` | Signal track (bedGraph) |

## narrowPeak Format

Columns: chrom, start, end, name, score, strand, signalValue, pValue, qValue, summit_offset

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `macs3` | macs3, homer, genrich |
| `--mode` | `atac` | atac, chipseq |
| `--genome` | `hs` | hs (human), mm (mouse) |
| `--qvalue` | `0.05` | FDR threshold |

## Why This Exists

- **Without it**: Open chromatin peaks are modeled with poor shifting logic or non-reproducible parameters
- **With it**: ATAC-specific logic correctly infers true transposase insertions vs nucleosomes
- **Why OmicsClaw**: Exposes high-level biology queries directly mapped to strictly modeled peak calling routines

## Workflow

1. **Calculate**: Prepare cross-correlation and fragment histograms.
2. **Execute**: Test local enrichment over poisson distribution null.
3. **Assess**: Perform IDR replicates and FDR significance tests.
4. **Generate**: Output structured summit maps and bedGraph.
5. **Report**: Tabulate core peaks and TF motifs.

## Example Queries

- "Run ATAC peak calling with MACS3 on this bam file"
- "Perform motif analysis on epigenomics data BED"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── peaks.narrowPeak
├── figures/
│   └── footprint_plot.png
├── tables/
│   └── motif_enrichment.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `align` — Upstream generation of BAM
- `genomics-qc` — Upstream filtering

## Version Compatibility

Reference examples tested with: MACS3 3.0+, samtools 1.19+

## Dependencies

**Required**: MACS3 (macs3), samtools
**Optional**: Homer, Genrich, IDR, bedtools, pyGenomeTracks

## Citations

- [MACS3](https://doi.org/10.1186/gb-2008-9-9-r137) — Zhang et al., Genome Biology 2008
- [Homer](http://homer.ucsd.edu/) — Heinz et al., Molecular Cell 2010
- [IDR](https://doi.org/10.1214/11-AOAS466) — Li et al., Annals of Applied Statistics 2011
- [ATAC-seq](https://doi.org/10.1038/nmeth.2688) — Buenrostro et al., Nature Methods 2013

## Related Skills

- `genomics-qc` — QC before peak calling
- `align` — Read alignment upstream
