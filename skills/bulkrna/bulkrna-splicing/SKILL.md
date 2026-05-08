---
name: bulkrna-splicing
description: >-
  Alternative splicing analysis — PSI quantification, differential splicing event
  detection from rMATS/SUPPA2 output.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, splicing, alternative-splicing, PSI, rMATS, SUPPA2]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🧬"
    trigger_keywords: [alternative splicing, splicing analysis, PSI, rMATS, SUPPA2,
      exon skipping, differential splicing]
    allowed_extra_flags:
    - "--dpsi-cutoff"
    - "--padj-cutoff"
    legacy_aliases: [bulk-splicing]
    saves_h5ad: false
    script: bulkrna_splicing.py
    param_hints: {}
    requires_preprocessed: false
---

# Bulk RNA-seq Alternative Splicing Analysis

Alternative splicing quantification and differential splicing event detection. Accepts pre-computed splicing event tables (e.g. from rMATS or SUPPA2), computes PSI-based statistics, identifies significant differential splicing events, and produces publication-ready visualizations.

## CLI Reference

```bash
python omicsclaw.py run bulkrna-splicing --demo
python omicsclaw.py run bulkrna-splicing --input <splicing_events.csv> --output <dir>
python bulkrna_splicing.py --input events.csv --output results/ --dpsi-cutoff 0.1 --padj-cutoff 0.05
python bulkrna_splicing.py --demo --output /tmp/splicing_demo
```

## Why This Exists

- **Without it**: Researchers must manually parse rMATS/SUPPA2 output files, compute delta-PSI statistics, apply multiple-testing correction, and create splicing-specific visualizations across thousands of events.
- **With it**: A single Python command summarizes splicing events by type, identifies significant differential splicing, and produces volcano plots and event-type distributions ready for publication.
- **Why OmicsClaw**: Wraps standard alternative splicing analysis into the OmicsClaw reporting framework with consistent output structure, reproducibility scripts, and automatic demo data generation.

## Algorithm / Methodology

### Splicing Event Types

| Abbreviation | Event Type | Description |
|---|---|---|
| SE | Skipped Exon | An exon is included or excluded from the transcript |
| A5SS | Alternative 5' Splice Site | Two or more 5' splice sites for the same exon |
| A3SS | Alternative 3' Splice Site | Two or more 3' splice sites for the same exon |
| MXE | Mutually Exclusive Exons | One of two exons is included, not both |
| RI | Retained Intron | An intron is retained in the mature transcript |

### PSI Quantification

Percent Spliced In (PSI) measures the fraction of transcripts that include a given exon or splice site:

```
PSI = inclusion_reads / (inclusion_reads + exclusion_reads)
```

Delta-PSI (dPSI) between conditions:

```
dPSI = PSI_treatment - PSI_control
```

### Statistical Testing

- **Per-event t-test**: Welch's t-test on PSI replicates between conditions
- **Multiple testing correction**: Benjamini-Hochberg FDR
- **Significance thresholds**: |dPSI| > cutoff AND padj < cutoff

### Upstream Tools

This skill operates on pre-computed splicing event tables produced by:

- **rMATS** (replicate Multivariate Analysis of Transcript Splicing) — detects differential alternative splicing from replicate RNA-seq data
- **SUPPA2** — fast quantification of splicing events from transcript-level TPMs

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | — | Path to splicing events CSV |
| `--output` | — | Output directory (required) |
| `--demo` | — | Run with synthetic demo data |
| `--dpsi-cutoff` | `0.1` | Absolute delta-PSI threshold for significance |
| `--padj-cutoff` | `0.05` | Adjusted p-value threshold for significance |

## Workflow

1. **Load**: Read a splicing events table (CSV with event_id, event_type, gene, psi_ctrl, psi_treat, delta_psi, pvalue, padj columns).
2. **Summarize**: Count events by type, compute overall statistics.
3. **Filter**: Identify significant differential splicing events by |dPSI| and adjusted p-value thresholds.
4. **Visualize**: Generate event type distribution (pie chart), delta-PSI histogram, and splicing volcano plot.
5. **Report**: Write markdown report, result.json, full and filtered event tables, and a reproducibility script.

## Example Queries

- "Analyze alternative splicing events from my rMATS output"
- "Find significant differential splicing between conditions"
- "Show me the distribution of splicing event types"
- "Run splicing analysis with a delta-PSI cutoff of 0.15"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── event_type_distribution.png
│   ├── dpsi_distribution.png
│   └── volcano_splicing.png
├── tables/
│   ├── splicing_events.csv
│   └── significant_events.csv
└── reproducibility/
    └── commands.sh
```

## Safety

- **Local-first**: All processing runs locally; no data is uploaded to external services.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.
- **Audit trail**: Parameters, thresholds, and input metadata are recorded in result.json.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked when user intent matches alternative splicing analysis keywords.

**Chaining partners**:
- `bulkrna-qc` — Upstream: count matrix QC
- `bulkrna-de` — Parallel: gene-level differential expression to complement exon-level splicing
- `bulkrna-enrichment` — Downstream: pathway enrichment of genes with significant splicing changes

## Version Compatibility

Reference examples tested with: scipy 1.11+, pandas 2.0+, numpy 1.24+, matplotlib 3.7+

## Dependencies

**Required**: numpy, pandas, scipy, matplotlib

## Citations

- [rMATS](https://doi.org/10.1073/pnas.1419161111) — Shen et al., PNAS 2014
- [SUPPA2](https://doi.org/10.1101/gr.213454.116) — Trincado et al., Genome Research 2018
- [Benjamini-Hochberg](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) — Benjamini & Hochberg, JRSSB 1995

## Related Skills

- `bulkrna-qc` — Count matrix QC upstream
- `bulkrna-de` — Gene-level differential expression
- `bulkrna-enrichment` — Pathway enrichment of affected genes
