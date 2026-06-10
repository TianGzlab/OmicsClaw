# Methodology — bulkatac-mapping

## Capabilities

Bulk ATAC-seq ENCODE Step 2 — alignment + post-alignment QC. Concretely:

- **Reference preparation** — auto-downloads FASTA + ENCODE blacklist for known builds (hg38, mm10, sacCer3, …), builds Bowtie2 or BWA index in `--ref-dir`. Skips if `--bwa-index` / `--bowtie2-index` is supplied.
- **Alignment** — Bowtie2 with ENCODE / CebolaLab parameters (`--very-sensitive --no-mixed --no-discordant -I 25 -X 700` PE; `--very-sensitive` SE) or BWA MEM with default flags.
- **ENCODE BAM filter** — `samtools view -F 1804 -f 2 -q 30` (PE) or `-F 1796 -q 30` (SE). MAPQ ≥ 30 is hard-coded.
- **chrM removal** — drop reads on `chrM` / `MT` / `M` after the MAPQ filter.
- **Duplicate removal** — `samtools markdup -r`.
- **(Optional) blacklist subtract** — `bedtools intersect -v` against the ENCODE blacklist BED.
- **Library complexity** — NRF, PBC1, PBC2 from the deduplicated BAM (counted per fragment for PE).
- **(Optional) cross-sample downsampling** — when `--downsample` is set, all samples are downsampled to `min(n_usable)` for DA fairness (see Reske et al. 2020).
- **BigWig signal** — deepTools `bamCoverage --normalizeUsing RPGC --binSize 10 --ignoreDuplicates --minMappingQuality 30`.
- **TSS enrichment** — deepTools `computeMatrix reference-point` over the genome's GTF TSS coordinates; produces per-sample profile + cohort overlay + (hg38/mm10) `vs_encode` comparison.
- **Fragment-length distribution** — TLEN-based histogram per sample + cohort overlay; computes modal fragment length, nucleosome-free (< 100 bp) and mono-nucleosome (180-247 bp) fractions.

What this skill does NOT do (handed off to downstream skills):

- Peak calling, FRiP, IDR → `bulkatac-peak-calling`
- Peak annotation → `bulkatac-peak-calling` (or a future `bulkatac-peak-annotation` skill)
- Differential accessibility → `bulkatac-da`
- Tn5 shift (+4/-5) — left to downstream tools (TOBIAS `ATACorrect`, MACS2 `--shift`/`--extsize`). Pre-shifting here would double-correct.

## Workflow

1. **Locate Step-1 result** — `--prev-result` is explicit, otherwise auto-detected at `<wd>/preprocessing/result.json`. Hard-fail if neither resolves.
2. **Reconstruct SampleSheet** — `load_mapping_result` rebuilds `Sample` and `SampleSheet` objects from the Step-1 JSON; trimmed-FASTQ paths come from the `preprocessing` array.
3. **Resolve `--genome`** — CLI overrides the value recorded by Step 1; hard-fail if both are absent.
4. **Resolve reference** — if `--bwa-index` / `--bowtie2-index` supplied, use as-is; otherwise call `prepare_reference` (downloads FASTA via `wget`, builds index, downloads ENCODE blacklist unless `--no-blacklist`).
5. **Step 2a — `run_all_mapping`** — per sample: align → ENCODE filter → chrM removal → markdup → optional blacklist subtract → NRF/PBC. Cross-sample downsample only when `--downsample` is set.
6. **Step 2b — `run_all_qc_after_mapping`** — per sample: BigWig (RPGC), TSS enrichment, fragment-length stats. Combines per-sample PNGs into cohort overlays.
7. **Emit outputs** — `mapping_summary.csv`, `qc_after_mapping_summary.csv`, `report.md`, `result.json`, `reproducibility/`, `README.md`, then a stdout completion summary.

## Methodology — per-step details

### Bowtie2 parameters (ENCODE / CebolaLab)

- **Paired-end**: `--very-sensitive --no-mixed --no-discordant -I 25 -X 700` — only proper pairs with insert size 25–700 bp are retained; sensitivity dialled up because ATAC fragments are often shorter and the genome is non-trivial.
- **Single-end**: `--very-sensitive` — no insert-size constraints (no mate).

### BWA MEM parameters

- Default flags — `bwa mem -t <threads>`. No `-k`, `-r`, or `-M` overrides. The ENCODE-style filter applied downstream is what enforces uniqueness (`-q 30`).

### ENCODE BAM filter — flag derivation

- **PE**: `-F 1804 -f 2 -q 30` excludes unmapped / mate-unmapped / secondary / qc-fail / duplicate / supplementary (1804 = 4 + 8 + 256 + 512 + 1024); requires proper-pair (2); MAPQ ≥ 30.
- **SE**: `-F 1796 -q 30` — same exclusion set minus the mate-unmapped bit (8), no proper-pair requirement.
- MAPQ threshold is hard-coded at 30 (not configurable). Reads at MAPQ 1–29 are dropped, which on repeat-rich genomes can substantially reduce usable depth.

### Library complexity (NRF, PBC1, PBC2)

Computed per the ENCODE ATAC SOP from the deduplicated BAM:

- `NRF` = distinct unique-mapping fragments / total unique-mapping fragments. ENCODE tiers: `> 0.90` ideal, `> 0.80` acceptable.
- `PBC1` = fragments observed once / distinct fragments. `> 0.90` ideal, `> 0.50` acceptable; `< 0.50` indicates severe PCR bottleneck.
- `PBC2` = fragments observed once / fragments observed twice. `> 3.0` ideal, `> 1.0` acceptable.

### Cross-sample downsampling (`--downsample`)

ENCODE does NOT downsample; the pipeline relies on RPGC for visualisation and DESeq2 / edgeR size factors for differential accessibility. However, Reske et al. 2020 (PMID 32321567) showed library-complexity differences confound DA results and recommend subsampling to equivalent complexity prior to normalisation. The flag is opt-in for that reason.

When set, the target is `min(n_usable)` across the cohort; per-sample downsampled BAMs land at `bam/<sample>.downsampled.bam`. The full-depth BAM is retained alongside.

### BigWig signal — RPGC normalisation

`bamCoverage --normalizeUsing RPGC --binSize 10 --ignoreDuplicates --minMappingQuality 30`.

- **RPGC** = reads per genomic content — divides each bin's count by an effective genome size and the total read count. Comparable across samples regardless of depth.
- **10 bp bins** — fine enough for sub-peak resolution, coarse enough to keep BigWig file size sane.
- **`--ignoreDuplicates` + `--minMappingQuality 30`** — re-applies the dedup + MAPQ filter to be defensive against external BAMs that haven't been through the ENCODE pipeline.
- **Effective genome size** is looked up from the deepTools table (per the docstring reference at `bulkatac-mapping.py:72`).

### TSS enrichment

- Compute matrix via `deepTools computeMatrix reference-point` over TSS coordinates from the genome's GTF (gene-level start positions).
- Score = mean signal in the TSS ± 1 kb window divided by mean signal in the flanking baseline.
- Tier assignment uses `--cell-type`: cell-line cohorts get `> 7.0 ideal`, `> 5.0 acceptable`; tissue cohorts get `> 5.0 ideal`, `> 3.0 acceptable`. Omitting `--cell-type` skips tier assignment but still computes the score.
- For hg38 / mm10, a `vs_encode` comparison overlay against published reference TSS profiles is generated.

### Fragment-length distribution

- Per sample: histogram of `|TLEN|` for properly-paired primary alignments.
- Modal fragment length, `nfr_fraction` (< 100 bp, nucleosome-free), `mono_fraction` (180-247 bp, mono-nucleosome) reported in the QC summary.
- Healthy ATAC libraries show a clear NFR peak and one or more nucleosome peaks; loss of nucleosome periodicity suggests over-digestion or low signal-to-noise.

## Demo

This skill has NO `--demo` flag. Smoke-test the full Step 1 → Step 2 chain
by running `bulkatac-preprocessing --demo` first; its `result.json` is
valid input here and the sacCer3 reference auto-downloads in seconds.

## Dependencies

**Python packages** (declared in SKILL.md `requires`):

- `pandas` — DataFrame assembly for summary CSVs.
- `numpy` — transitive (pandas).

**External tools** (must be on `PATH`):

- `bowtie2` or `bwa` (one of, matching `--aligner`)
- `samtools` (for sort, view, markdup, index, flagstat)
- `bedtools` (only when blacklist subtract triggers)
- `deeptools` (`bamCoverage`, `computeMatrix`, `plotProfile`)
- `wget` or `curl` (only when reference is auto-downloaded)

**Tested versions**: bowtie2 ≥ 2.4, bwa ≥ 0.7.17, samtools ≥ 1.15, bedtools ≥ 2.30, deepTools ≥ 3.5.

## References

- Langmead B, Salzberg SL (2012). Fast gapped-read alignment with Bowtie 2.
  *Nat. Methods* 9:357–359. <https://doi.org/10.1038/nmeth.1923>
- Li H (2013). Aligning sequence reads, clone sequences and assembly contigs
  with BWA-MEM. arXiv:1303.3997.
- Danecek P, et al. (2021). Twelve years of SAMtools and BCFtools.
  *GigaScience* 10:giab008. <https://doi.org/10.1093/gigascience/giab008>
- Quinlan AR, Hall IM (2010). BEDTools: a flexible suite of utilities for
  comparing genomic features. *Bioinformatics* 26:841–842.
  <https://doi.org/10.1093/bioinformatics/btq033>
- Ramírez F, et al. (2016). deepTools2: a next-generation web server for
  deep-sequencing data analysis. *Nucleic Acids Res.* 44:W160–W165.
  <https://doi.org/10.1093/nar/gkw257>
- Reske JJ, Wilson MR, Chandler RL (2020). ATAC-seq normalization method can
  significantly affect differential accessibility analysis and interpretation.
  *Epigenetics & Chromatin* 13:22. PMID 32321567 — basis of `--downsample`.
- ENCODE ATAC-seq pipeline — <https://www.encodeproject.org/atac-seq/> —
  BAM-filter flags, NRF/PBC1/PBC2 and TSS-enrichment QC.
- CebolaLab ATAC-seq — <https://github.com/CebolaLab/ATAC-seq>
