# Output Contract — bulkchip-mapping

> Scaffold: intended outputs once the tool-backed body is implemented.

## Output Structure

```
<output>/
├── README.md
├── report.md
├── result.json                        # chained from Step 1
├── mapping_summary.csv                # per-sample align + complexity
├── bam/                               # dedup BAMs (ChIP + control), flat
├── bigwig/                            # per-sample RPGC tracks + *.log2_input.bw (log2 ChIP/input)
├── reproducibility/
└── qc_after_mapping/
    ├── qc_after_mapping_summary.csv   # NSC/RSC + fingerprint per ChIP sample
    ├── cross_correlation/             # run_spp.R / ssp cross-corr plots
    └── fingerprint/                   # deepTools plotFingerprint PNGs
```

## File Contents

### `result.json`

```json
{
  "skill": "bulkchip-mapping",
  "version": "0.1.0",
  "steps_completed": ["preprocessing", "mapping", "qc_after_mapping"],
  "params": { "aligner": "bwa-mem2", "threads": 16, "downsample": false },
  "mapping": [
    { "sample": "...", "bam": "...", "aligner": "bwa-mem2", "is_control": false,
      "align_rate": 0.0, "n_fragments": 0, "pct_mito": 0.0,
      "nrf": 0.0, "pbc1": 0.0, "pbc2": 0.0, "downsampled": false }
  ],
  "qc_after_mapping": [
    { "sample": "...", "nsc": 0.0, "rsc": 0.0, "nsc_tier": "...", "rsc_tier": "...",
      "est_frag_len": 0, "fingerprint_js": 0.0, "bigwig": "...",
      "bigwig_log2_input": "..." }
  ],
  "encode_qc_thresholds": { /* from _lib.encode_qc_criteria */ },
  "genome_files": { "genome": "hg38", "fasta": "...", "gtf": "...", "blacklist": "...", "chrom_sizes": "..." },
  "control_map": { "<chip_sample>": "<control_sample>" },
  "sample_sheet": { /* carried forward */ },
  "prev_result": "<absolute path to Step 1 result.json>"
}
```

### `mapping_summary.csv`

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name |
| `is_control` | bool | True for input/IgG |
| `align_rate` | float | uniquely-mapped fraction |
| `n_fragments` | int | usable fragments/reads post-filter |
| `pct_mito` | float | % mitochondrial (pre-removal) |
| `nrf` | float | Non-Redundant Fraction |
| `pbc1` | float | PCR Bottleneck Coefficient 1 |
| `pbc2` | float | PCR Bottleneck Coefficient 2 (ENCODE ChIP bar > 10) |

### `qc_after_mapping/qc_after_mapping_summary.csv`

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | ChIP sample name |
| `nsc` | float | normalized strand cross-correlation (acceptable > 1.05) |
| `rsc` | float | relative strand cross-correlation (acceptable > 0.8) |
| `est_frag_len` | int | cross-correlation fragment-length estimate (bp) |
| `fingerprint_js` | float | deepTools fingerprint JS distance vs matched input |
