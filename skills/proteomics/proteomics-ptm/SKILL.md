---
name: proteomics-ptm
description: >-
  Post-translational modification analysis including phosphorylation, acetylation,
  and ubiquitination. Site localization, motif analysis, and quantitative PTM
  analysis with MSstatsPTM.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [proteomics, PTM, phosphorylation, acetylation, motif]
metadata:
  omicsclaw:
    domain: proteomics
    emoji: "🔬"
    trigger_keywords: [PTM, phosphorylation, acetylation, ubiquitination, modification, motif]
---

# 🔬 Post-Translational Modification Analysis

Identify, quantify, and analyze post-translational modifications from mass spectrometry data.

## Core Capabilities

1. **MaxQuant PTM output processing**: Filter by localization probability, site annotation
2. **Site localization scoring**: A-score calculation for confident PTM site assignment
3. **Motif analysis**: Extract and count amino acid motifs around modification sites
4. **MSstatsPTM**: Site-level quantification with protein-level normalization
5. **Differential PTM analysis**: Adjusted for protein-level abundance changes

## CLI Reference

```bash
python omicsclaw.py run proteomics-ptm --demo
python omicsclaw.py run proteomics-ptm --input <phospho_sites.txt> --output <dir>
```

## Common PTMs and Mass Shifts

```python
PTM_MASSES = {
    'Phosphorylation': 79.966331,      # STY
    'Oxidation': 15.994915,             # M
    'Acetylation': 42.010565,           # K, N-term
    'Methylation': 14.015650,           # KR
    'Dimethylation': 28.031300,         # KR
    'Trimethylation': 42.046950,        # K
    'Ubiquitination': 114.042927,       # K (GlyGly remnant)
    'Deamidation': 0.984016,            # NQ
    'Carbamidomethyl': 57.021464,       # C (fixed mod from IAA)
}
```

## Algorithm / Methodology

### Processing MaxQuant PTM Output

```python
import pandas as pd
import numpy as np

# Phospho(STY)Sites.txt from MaxQuant
phospho = pd.read_csv('Phospho (STY)Sites.txt', sep='\t', low_memory=False)

# Filter valid sites
phospho = phospho[
    (phospho['Reverse'] != '+') &
    (phospho['Potential contaminant'] != '+')
]

# Filter by localization probability
phospho_confident = phospho[phospho['Localization prob'] >= 0.75]
print(f'Confident sites (prob >= 0.75): {len(phospho_confident)}')

# Extract site information
phospho_confident['site'] = phospho_confident.apply(
    lambda r: f"{r['Gene names']}_{r['Amino acid']}{r['Position']}", axis=1
)
```

### Site Localization Scoring

```python
def calculate_ascore_simple(peak_matches_with_ptm, peak_matches_without_ptm, total_peaks):
    '''Simplified A-score calculation'''
    if peak_matches_without_ptm >= peak_matches_with_ptm:
        return 0
    p = peak_matches_with_ptm / total_peaks if total_peaks > 0 else 0
    if p <= 0 or p >= 1:
        return 0

    from scipy.stats import binom
    p_value = 1 - binom.cdf(peak_matches_with_ptm - 1, total_peaks, 0.5)
    return -10 * np.log10(p_value) if p_value > 0 else 100
```

### Motif Analysis

```python
from collections import Counter

def extract_motifs(sites_df, sequence_col, position_col, window=7):
    '''Extract sequence windows around modification sites'''
    motifs = []
    for _, row in sites_df.iterrows():
        seq = row[sequence_col]
        pos = row[position_col] - 1  # 0-indexed
        start = max(0, pos - window)
        end = min(len(seq), pos + window + 1)

        # Pad if at sequence boundary
        motif = '_' * (window - (pos - start)) + seq[start:end] + '_' * (window - (end - pos - 1))
        motifs.append(motif)

    return motifs

def count_amino_acids_by_position(motifs, center=7):
    '''Count amino acid frequencies by position'''
    position_counts = {i: Counter() for i in range(-center, center + 1)}
    for motif in motifs:
        for i, aa in enumerate(motif):
            position_counts[i - center][aa] += 1
    return position_counts
```

### MSstatsPTM Site-Level Quantification (R)

```r
library(MSstatsPTM)

# Prepare input from MaxQuant
ptm_input <- MaxQtoMSstatsPTMFormat(
    evidence = read.table('evidence.txt', sep = '\t', header = TRUE),
    annotation = read.csv('annotation.csv'),
    fasta = 'uniprot_human.fasta',
    mod_type = 'Phospho'
)

# Process data
processed_ptm <- dataSummarizationPTM(ptm_input, method = 'msstats')

# Differential PTM analysis (adjusting for protein-level changes)
ptm_results <- groupComparisonPTM(processed_ptm, contrast.matrix = comparison_matrix)
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `maxquant` | maxquant, msstatsptm, custom |
| `--mod-type` | `Phospho` | PTM type to analyze |
| `--loc-prob` | `0.75` | Localization probability threshold |
| `--motif-window` | `7` | Motif window size |

## Why This Exists

- **Without it**: Phosphorylation counts are meaningless if not normalized against total protein abundance
- **With it**: Decouples actual post-translational regulatory changes from sheer protein expression changes
- **Why OmicsClaw**: Streamlines complex localization scoring and statistical corrections (MSstatsPTM)

## Workflow

1. **Calculate**: Localise modifications using probabilistic scoring.
2. **Execute**: Map sites to host proteins and correct for total abundance.
3. **Assess**: Perform differential PTM abundance testing.
4. **Generate**: Output motif logos and differential statistics.
5. **Report**: Synthesize site-level Volcano plots and motif tables.

## Example Queries

- "Run phosphoproteomics analysis on these MaxQuant sites"
- "Identify enriched motifs in hyper-phosphorylated peptides"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── confident_sites.csv
├── figures/
│   ├── motif_logo.png
│   └── site_volcano.png
├── tables/
│   ├── differential_ptm.csv
│   └── motif_counts.csv
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
- `peptide-id` — Upstream sequence identification
- `quantification` — Upstream total protein normalization

## Version Compatibility

Reference examples tested with: numpy 1.26+, pandas 2.2+, scipy 1.12+

## Dependencies

**Required**: numpy, pandas, scipy
**Optional**: MSstatsPTM (R), pyopenms

## Citations

- [MaxQuant](https://doi.org/10.1038/nbt.1511) — Cox & Mann, Nature Biotechnology 2008
- [MSstatsPTM](https://doi.org/10.1074/mcp.TIR122.002049) — Kohale et al., MCP 2023
- [Phosphosite localization](https://doi.org/10.1074/mcp.T400009-MCP200) — Beausoleil et al., MCP 2006

## Related Skills

- `peptide-id` — Identify modified peptides upstream
- `quantification` — Quantify PTM site intensities
- `prot-enrichment` — Pathway enrichment of modified proteins
