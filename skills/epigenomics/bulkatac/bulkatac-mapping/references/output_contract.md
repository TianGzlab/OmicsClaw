# Output Contract — bulkatac-mapping

## Output Structure

All skill outputs land directly under the skill's `--output` directory —
the OmicsClaw per-skill layout (no nested `mapping/` subdir). The reference
(if auto-downloaded) lands at `<project>/reference_<genome>/`, a sibling of
`--output`, so it can be shared across pipeline steps.

```
<output>/                                 # the --output directory
├── README.md                             # orientation note
├── report.md                             # markdown summary
├── result.json                           # structured envelope (chained from Step 1)
├── mapping_summary.csv                   # per-sample alignment + complexity
├── bam/
│   ├── <sample>.dedup.bam                # filtered + dedup (final BAM in default path)
│   ├── <sample>.no_blacklist.bam         # final BAM when a blacklist BED is applied
│   ├── <sample>.dedup.bam.bai            # index next to the final BAM
│   ├── <sample>.ds.bam                   # only when --downsample (cross-sample equalised)
│   ├── <sample>.raw.bam                  # only with --keep-intermediates
│   ├── <sample>.filtered.bam             # only with --keep-intermediates
│   └── <sample>.no_mito.bam              # only with --keep-intermediates
├── bigwig/
│   └── <sample>.rpgc.bw                  # deepTools bamCoverage RPGC track
├── qc_after_mapping/
│   ├── qc_after_mapping_summary.csv      # per-sample TSS + fragment-length scores
│   ├── tss_enrichment/                   # per-sample profiles + cohort overlay + vs_encode
│   └── fragment_length/                  # per-sample histogram + cohort overlay
└── reproducibility/
    ├── commands.sh
    └── requirements.txt

<project>/reference_<genome>/              # sibling of --output — only when auto-downloaded
├── <genome>.fa[.gz]
├── bowtie2/<genome>.{1..4,rev.1,rev.2}.bt2
├── bwa/<genome>.fa.{amb,ann,bwt,pac,sa}
└── <blacklist>.bed.gz                     # ENCODE blacklist (e.g. ENCFF356LFX)
```

## File Contents

### `report.md`

Markdown summary with four sections:

1. **Step 2a — Alignment and BAM Filtering** — sample table with `Align%`, `Frags`, `%mito`, `NRF`, `PBC1`, `PBC2`, and `DS` (downsample target or `—`).
2. **Step 2b — Post-alignment QC** — TSS / fragment-length table (only emitted when at least one sample's TSS score is computed): `TSS score`, `Tier`, `Frag mode`, `NFR%`, `Mono%`.
3. **ENCODE QC Thresholds** — preferred / acceptable cutoffs for NRF, PBC1, PBC2, fragment count, alignment rate, %mito, TSS enrichment.
4. **Usable read rule** — inline rendering of `UsableReadRule.description()` (the samtools include / exclude flag combination used to count usable reads).

### `result.json`

```json
{
  "skill": "bulkatac-mapping",
  "version": "0.1.0",
  "steps_completed": [..."mapping", "qc_after_mapping"],
  "steps_pending":   [/* Step 1 list with mapping / qc_after_mapping removed */],
  "params": { /* aligner, threads, *_index, blacklist, downsample, keep_intermediates, ref_dir, cell_type */ },
  "mapping": [
    {
      "sample": "...", "bam": "...", "bam_full": "...", "aligner": "bowtie2",
      "n_total_reads": ..., "n_mapped_reads": ..., "n_fragments": ...,
      "align_rate": ..., "pct_mito": ..., "dup_rate": ...,
      "nrf": ..., "pbc1": ..., "pbc2": ...,
      "downsampled": false, "downsample_target": null
    }
  ],
  "qc_after_mapping": [
    {
      "sample": "...", "tss_score": ..., "tss_tier": "...",
      "frag_mode_bp": ..., "nfr_fraction": ..., "mono_fraction": ...,
      "bigwig": "<output>/bigwig/<sample>.rpgc.bw"
    }
  ],
  "encode_qc_thresholds": { /* the ENCODE_QC_THRESHOLDS dict verbatim */ },
  "usable_read_rule":     { /* layout, samtools flags, mapq_threshold, exclude_contigs */ },
  "genome_files":         { /* genome, fasta, gtf, blacklist, chrom_sizes */ },
  "sample_sheet":         { /* carried forward from Step 1 result.json */ },
  "prev_result":          "<absolute path to Step 1 result.json>",
  "prev_params":          { /* Step 1 params */ },
  "prev_preprocessing":   [ /* Step 1 per-sample preprocessing entries */ ]
}
```

### `mapping_summary.csv`

One row per sample (built by `_lib.mapping.build_mapping_summary` at
`_lib/mapping.py:1348-1376`):

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name |
| `aligner` | str | `bowtie2` or `bwa` |
| `n_total_reads` | int | total reads in input FASTQ |
| `n_uniquely_mapped` | int | reads passing the ENCODE BAM filter (MAPQ ≥ 30, proper pair for PE) |
| `align_rate` | float | `n_uniquely_mapped / n_total_reads`, rounded to 4 dp |
| `mito_fraction` | float | fraction of mapped reads on chrM / MT / M, rounded to 4 dp |
| `n_non_duplicate` | int | reads remaining after `samtools markdup -r` |
| `n_usable` | int | usable reads per the layout-specific `UsableReadRule` |
| `dup_rate` | float | duplicate fraction, rounded to 4 dp |
| `nrf` | float | non-redundant fraction (rounded 4 dp) |
| `pbc1` | float | PCR bottleneck coefficient 1 (rounded 4 dp) |
| `pbc2` | float | PCR bottleneck coefficient 2 (rounded 3 dp) |
| `align_tier` | str | ENCODE tier label for `align_rate` |
| `nrf_tier` | str | ENCODE tier label for NRF |
| `pbc1_tier` | str | ENCODE tier label for PBC1 |
| `pbc2_tier` | str | ENCODE tier label for PBC2 |
| `downsampled` | bool | `True` if `--downsample` triggered cross-sample subsampling |
| `downsample_target` | int | target fragment count (min usable across cohort) — `0` when not downsampled |
| `bam` | str | absolute path to the deduplicated BAM |
| `bam_downsampled` | str | absolute path to the downsampled BAM (empty string if absent) |

### `qc_after_mapping/qc_after_mapping_summary.csv`

One row per sample (built by `_lib.QC_after_mapping.build_qc_after_mapping_summary`
at `_lib/QC_after_mapping.py:817-833`):

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name |
| `tss_score` | float | TSS enrichment score (peak / flanking baseline), rounded 2 dp |
| `tss_tier` | str | ENCODE tier label (`ideal` / `acceptable` / `concerning`) — varies by `--cell-type` |
| `frag_mode_bp` | int | modal fragment length (bp) |
| `nfr_fraction` | float | fraction of fragments in the nucleosome-free region (< 100 bp), 4 dp |
| `mono_fraction` | float | fraction of fragments at the mono-nucleosome peak (180–247 bp), 4 dp |
| `bigwig` | str | absolute path to the RPGC BigWig (empty string when BigWig generation skipped) |

### `bam/<sample>.dedup.bam` (+ `.bai`)

Coordinate-sorted, indexed BAM after the full ENCODE filter chain.
Renamed to `<sample>.no_blacklist.bam` when a blacklist BED is supplied.
`r.bam` in `result.json["mapping"]` points at whichever is the final
artefact:

- Bowtie2 / BWA alignment with the parameters at `bulkatac-mapping.py:42-43`
- `samtools view -F 1804 -f 2 -q 30` (PE) or `-F 1796 -q 30` (SE) — MAPQ ≥ 30
- Mitochondrial contigs removed
- `samtools markdup -r` removes duplicates
- Optional ENCODE blacklist subtract via `bedtools intersect -v`
- Reads are NOT Tn5-shifted — downstream tools (TOBIAS, MACS2) apply the offset themselves

### `bigwig/<sample>.rpgc.bw`

deepTools `bamCoverage` BigWig:

- `--normalizeUsing RPGC` (reads per genomic content)
- `--binSize 10`
- `--ignoreDuplicates`
- `--minMappingQuality 30`
- Effective genome size pulled from deepTools' published table (per the docstring at `bulkatac-mapping.py:72`)

### `qc_after_mapping/tss_enrichment/`

Per-sample TSS-aggregate matrices + PNGs (deepTools `computeMatrix reference-point`
on the genome's GTF TSS coordinates). The directory also contains a cohort
overlay (`all`) and, for hg38 / mm10, a `vs_encode` comparison plot
benchmarking against ENCODE reference TSS profiles.

### `qc_after_mapping/fragment_length/`

Per-sample fragment-length histograms (samtools `view` → `awk` over the
TLEN column) + cohort overlay. Used to compute `frag_mode_bp`,
`nfr_fraction`, `mono_fraction` in the summary CSV.

### `reproducibility/commands.sh` + `requirements.txt`

Single-line `python bulkatac-mapping.py ...` invocation reproducing the run.
The `*_index` flag is the resolved path (post-prepare_reference), so
re-runs of `commands.sh` skip the download step. `requirements.txt` pins
`pandas` / `numpy`; external tools (`bowtie2`, `bwa`, `samtools`,
`deeptools`, `bedtools`) are NOT pinned here — record those via
`conda list` separately if exact reproduction matters.
