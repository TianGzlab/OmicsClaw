---
name: genomics-cnv-calling
description: >-
  Copy number variant detection from exome/WGS data using CNVkit, Control-FREEC,
  or GATK gCNV. Supports tumor-normal pairs, tumor-only, and germline modes.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [genomics, CNV, copy-number, CNVkit, GATK]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "📊"
    trigger_keywords: [CNV, copy number, amplification, deletion, CNVkit]
    allowed_extra_flags:
    - "--method"
    legacy_aliases: [cnv-calling]
    saves_h5ad: false
    script: genomics_cnv_calling.py
    param_hints: {}
    requires_preprocessed: false
---

# 📊 Copy Number Variant Calling

Detect copy number variants from targeted/exome/WGS sequencing data.

## Core Capabilities

1. **CNVkit**: Read-depth-based CNV detection for exome/targeted/WGS data
2. **GATK gCNV**: GATK's germline CNV discovery tool
3. **Control-FREEC**: Control-free copy number and LOH caller

## CLI Reference

```bash
python omicsclaw.py run cnv-calling --demo
python omicsclaw.py run cnv-calling --input <tumor.bam> --output <dir>
```

## Algorithm / Methodology

### CNVkit Basic Workflow

**Goal:** Run the complete CNVkit pipeline on a tumor-normal pair.

```bash
# Complete pipeline for tumor-normal pair
cnvkit.py batch tumor.bam \
    --normal normal.bam \
    --targets targets.bed \
    --fasta reference.fa \
    --output-reference my_reference.cnn \
    --output-dir results/
```

### Build Reference from Panel of Normals

```bash
# Step 1: Build reference from multiple normals (recommended)
cnvkit.py batch \
    --normal normal1.bam normal2.bam normal3.bam \
    --targets targets.bed \
    --fasta reference.fa \
    --output-reference pooled_reference.cnn

# Step 2: Run on tumor samples using pre-built reference
cnvkit.py batch tumor1.bam tumor2.bam \
    --reference pooled_reference.cnn \
    --output-dir results/
```

### Flat Reference (No Matched Normal)

```bash
cnvkit.py batch tumor.bam \
    --targets targets.bed \
    --fasta reference.fa \
    --output-reference flat_reference.cnn \
    --output-dir results/
```

### WGS Mode

```bash
cnvkit.py batch tumor.bam \
    --normal normal.bam \
    --fasta reference.fa \
    --method wgs \
    --output-dir results/
```

### Step-by-Step Pipeline

```bash
# 1. Generate target and antitarget regions
cnvkit.py target targets.bed --annotate refFlat.txt -o targets.target.bed
cnvkit.py antitarget targets.bed -o targets.antitarget.bed

# 2. Calculate coverage
cnvkit.py coverage tumor.bam targets.target.bed -o tumor.targetcoverage.cnn
cnvkit.py coverage tumor.bam targets.antitarget.bed -o tumor.antitargetcoverage.cnn
cnvkit.py coverage normal.bam targets.target.bed -o normal.targetcoverage.cnn
cnvkit.py coverage normal.bam targets.antitarget.bed -o normal.antitargetcoverage.cnn

# 3. Build reference
cnvkit.py reference normal.targetcoverage.cnn normal.antitargetcoverage.cnn \
    --fasta reference.fa -o reference.cnn

# 4. Fix, segment, and call
cnvkit.py fix tumor.targetcoverage.cnn tumor.antitargetcoverage.cnn reference.cnn -o tumor.cnr
cnvkit.py segment tumor.cnr -o tumor.cns
cnvkit.py call tumor.cns -o tumor.call.cns
```

### Segmentation Options

```bash
# Default CBS (Circular Binary Segmentation)
cnvkit.py segment sample.cnr -o sample.cns

# HMM for tumor samples (broader state transitions)
cnvkit.py segment sample.cnr --method hmm-tumor -o sample.cns

# HMM for germline (tighter priors around diploid)
cnvkit.py segment sample.cnr --method hmm-germline -o sample.cns
```

### CNV Calling with Ploidy/Purity

```bash
cnvkit.py call sample.cns --purity 0.7 --ploidy 2 -o sample.call.cns

# With B-allele frequencies (from VCF)
cnvkit.py call sample.cns --vcf sample.vcf --purity 0.7 -o sample.call.cns
```

### Visualization

```bash
# Scatter plot with segments
cnvkit.py scatter sample.cnr -s sample.cns -o sample_scatter.png

# Single chromosome
cnvkit.py scatter sample.cnr -s sample.cns -c chr17 -o sample_chr17.png

# Diagram (ideogram style)
cnvkit.py diagram sample.cnr -s sample.cns -o sample_diagram.pdf

# Heatmap across samples
cnvkit.py heatmap *.cns -o heatmap.pdf
```

### Export Results

```bash
cnvkit.py export bed sample.call.cns -o sample.cnv.bed
cnvkit.py export vcf sample.call.cns -o sample.cnv.vcf
cnvkit.py export seg *.cns -o samples.seg          # For GISTIC2
```

### Python API

```python
import cnvlib

# Load data
cnr = cnvlib.read('sample.cnr')
cns = cnvlib.read('sample.cns')

# Filter by chromosome
chr17 = cnr[cnr.chromosome == 'chr17']

# log2 > 0.5 (~3+ copies): moderate amplification
amps = cns[cns['log2'] > 0.5]
# log2 < -0.5 (~1 copy): moderate deletion
dels = cns[cns['log2'] < -0.5]
```

### Quality Control

```bash
cnvkit.py metrics *.cnr -s *.cns
cnvkit.py sex *.cnr *.cnn
cnvkit.py segmetrics sample.cnr -s sample.cns --ci --pi -o sample.segmetrics.cns
cnvkit.py genemetrics sample.cnr -s sample.cns --threshold 0.2 --ci -o sample.genemetrics.tsv
```

## Key Output Files

| Extension | Description |
|-----------|-------------|
| `.cnn` | Reference or coverage file |
| `.cnr` | Copy ratios (log2) per bin |
| `.cns` | Segmented copy ratios |
| `.call.cns` | Called copy number states |

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `hybrid` | hybrid, wgs, amplicon |
| `--segment-method` | `cbs` | cbs, hmm, hmm-tumor, hmm-germline |
| `--purity` | `1.0` | Tumor purity (0-1) |
| `--ploidy` | `2` | Sample ploidy |

## Why This Exists

- **Without it**: Raw coverage depth is noisy due to GC-bias causing false structural variants
- **With it**: Strict background normalization and segmentation reveals true CNV events
- **Why OmicsClaw**: Wraps complex tools like CNVkit into reproducible one-shot commands

## Workflow

1. **Calculate**: Map out local depth coverage and background noise.
2. **Execute**: Evaluate log-ratio changes over target intervals.
3. **Assess**: Perform segmentation algorithms (e.g., CBS).
4. **Generate**: Output structural segments and variation boundaries.
5. **Report**: Tabulate key amplification/deletion events.

## Example Queries

- "Call copy number variants on this bam using CNVkit"
- "Detect amplifications in the tumor matched normal pair"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── segments.cns
├── figures/
│   └── scatter_diagram.png
├── tables/
│   └── cnv_calls.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
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
- `align` — Upstream BAM processing
- `annotation` — Downstream gene mapping of duplications

## Version Compatibility

Reference examples tested with: CNVkit 0.9+, GATK 4.5+

## Dependencies

**Required**: CNVkit (cnvkit.py)
**Optional**: GATK (for gCNV), Control-FREEC

## Citations

- [CNVkit](https://doi.org/10.1371/journal.pcbi.1004873) — Talevich et al., PLoS Computational Biology 2016
- [GATK gCNV](https://gatk.broadinstitute.org/) — Broad Institute
- [Control-FREEC](https://doi.org/10.1093/bioinformatics/btr670) — Boeva et al., Bioinformatics 2012

## Related Skills

- `variant-call` — SNV/Indel calling in same samples
- `sv-detect` — Structural variant detection
- `variant-annotate` — Annotate CNV regions
