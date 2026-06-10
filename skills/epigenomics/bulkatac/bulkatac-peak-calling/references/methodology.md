# Methodology — bulkatac-peak-calling

## Capabilities

Bulk ATAC-seq ENCODE Step 3 — peak calling, consensus, annotation, and
post-peak QC. Concretely:

- **Per-sample peak calling** — MACS2 `callpeak` per sample at `--qvalue`. PE uses `--format BAMPE --nomodel`; SE uses the half-nucleosome shift model (`--shift -37 --extsize 73`). Layout is inferred from Step-2 `sample_sheet`.
- **Consensus peaks (ENCODE naive overlap)** — per condition, pool BAMs → re-MACS2-call pooled set → intersect pooled peaks with each replicate at `--overlap-fraction` reciprocal overlap → union across conditions via `bedtools merge`.
- **Count matrix** — `featureCounts` on the consensus SAF using full-depth dedup BAMs (PE: fragment counting). Raw counts ready for DESeq2 / edgeR size factors downstream.
- **Peak annotation** — HOMER `annotatePeaks.pl` when available, else GTF-based `bedtools closest`. Per-condition annotation merges replicates then categorises peaks (`promoter` / `proximal` / `distal` / `intergenic`) and measures distance to nearest TSS. Cross-condition comparison panels generated when ≥ 2 conditions.
- **Post-peak QC** — FRiP per sample, TSS heatmap (deepTools), peak-centered heatmap, PCA (DESeq2 VST), sample correlation, optional ENCODE IDR reproducibility.

What this skill does NOT do (handed off downstream):

- Differential accessibility → `bulkatac-da` (consumes `consensus_peaks.saf` + `peak_counts.txt`).
- Motif enrichment → `bulkatac-motif-enrichment` (consumes consensus peaks).
- Footprinting → `bulkatac-footprinting` (consumes consensus peaks + BAMs).

## Workflow

1. **Locate Step-2 result** — `--prev-result` is explicit, else auto-detected at `<wd>/mapping/result.json`; hard-fail if absent.
2. **Reconstruct upstream state** — `load_step2_result` rebuilds `MappingResult` list + `GenomeFiles` + per-sample BigWig paths from the Step-2 envelope. CLI `--gtf` overrides any auto-detected GTF.
3. **Resolve MACS2 genome size** — `get_macs2_genome_size` returns the effective genome size for known builds (hg38 / mm10 / sacCer3) or falls back to FASTA-derived length.
4. **Step 3a — per-sample MACS2** — `run_all_peak_calling` per sample, writing `<sample>_peaks.narrowPeak` + `<sample>_summits.bed` under `peaks/<sample>/qvalue<q>/`.
5. **Step 3a (cont.) — consensus** — `build_consensus_peaks` runs the ENCODE naive-overlap algorithm and writes `consensus_peaks.bed` + `consensus_peaks.saf`.
6. **Step 3a (cont.) — count matrix** — `build_count_matrix` runs featureCounts and writes `peak_counts.txt`.
7. **Step 3b — annotation** — `annotate_per_condition_peaks` (HOMER or bedtools fallback) per condition + cross-condition comparison plots. Silently skipped (with a warning) when neither GTF nor HOMER is available.
8. **Step 3c — post-peak QC** — `compute_frip` per sample → `plot_frip_bar`; deepTools `plot_tss_heatmap` + `plot_peak_heatmap` over all samples' BigWigs; `plot_pca` + `plot_sample_correlation` on the count matrix (requires ≥ 2 conditions); optional `run_all_idr` + `plot_idr_summary` when `--idr` is set.
9. **Emit outputs** — `report.md`, `result.json`, `reproducibility/`, `README.md`, then a stdout completion summary.

## Methodology — per-step details

### MACS2 parameter derivation

- **Paired-end**: `macs2 callpeak --format BAMPE --nomodel -g <eff_genome_size> -q <qvalue>`. BAMPE uses the actual fragment endpoints, so the shift/extsize empirical model is unnecessary (and wrong).
- **Single-end**: `--shift -37 --extsize 73 --nomodel`. The half-nucleosome window (73 bp = ~half a nucleosome wrap) centered around the cut site is the ENCODE / Buenrostro 2013 default. `--shift -37` recenters the read on the Tn5 insertion site.
- **Effective genome size** is per build (hg38 ≈ 2.9 GB, mm10 ≈ 2.6 GB, sacCer3 ≈ 12 MB). For unknown builds the FASTA length minus `N` bases is used.
- **`--keep-dup all`** is supplied internally — duplicates were already removed by `samtools markdup -r` in Step 2, so MACS2 must not double-filter.

### ENCODE naive-overlap consensus

1. Per condition, BAMs of all replicates are pooled with `samtools merge`.
2. MACS2 is re-called on the pooled BAM with the same `--qvalue` / `--shift` / `--extsize` parameters.
3. The pooled peak set is intersected against each replicate's individual peak set via `bedtools intersect -wo -f <overlap_fraction> -F <overlap_fraction> -e` (reciprocal overlap ≥ `--overlap-fraction`, default 0.50 = ENCODE standard). A pooled peak survives if it overlaps at least one replicate's peak.
4. Per-condition reproducible peak sets are unioned across conditions with `bedtools merge -d 0` to produce the final `consensus_peaks.bed`.

Lower `--overlap-fraction` (e.g. 0.30) = more permissive consensus,
more peaks survive replicate disagreement.

### BED → SAF conversion

`bedtools` BED is 0-based half-open; SAF (featureCounts) uses 1-based
fully closed coordinates. The converter at `_lib.peak_calling` adds 1 to
the start; end remains unchanged. `GeneID` is `consensus_peak_<N>` so
the count matrix has stable, parseable row names.

### featureCounts invocation

```
featureCounts -F SAF -a consensus_peaks.saf -o peak_counts.txt \
  -T <threads> [-p --countReadPairs]   # PE only
  <sample_1.bam> <sample_2.bam> ...
```

- PE: `-p --countReadPairs` counts fragments (not reads) — ENCODE convention for DA.
- Unstranded; ATAC has no library strand orientation by design.
- Duplicate filtering already applied upstream (Step 2's `samtools markdup -r`).

### Peak annotation — HOMER vs bedtools

- **HOMER `annotatePeaks.pl`** — chosen when `shutil.which("annotatePeaks.pl")` succeeds AND the genome name is HOMER-recognised (e.g. `hg38`, `mm10`, `sacCer3`). HOMER carries its own annotation database per genome; no GTF needed. Faster + more category granularity (`promoter-TSS`, `5'UTR`, `exon`, `intron`, `intergenic`, `3'UTR`, `non-coding`, `TTS`).
- **bedtools `closest` fallback** — used when HOMER is absent OR the genome is unknown to HOMER but a GTF is supplied. Categorises by distance to nearest TSS: `promoter` (`|d| < 1 kb`), `proximal` (`1 ≤ |d| < 10 kb`), `distal` (`10 ≤ |d| < 100 kb`), `intergenic` (`|d| ≥ 100 kb`).

Both paths produce the same downstream artifacts (`<condition>_annotated.tsv`, pie, TSS-distance histogram).

### Post-peak QC details

- **FRiP** = (reads in consensus peaks) / (usable reads). ENCODE: `> 0.3` ideal, `> 0.2` acceptable.
- **TSS heatmap** — `computeMatrix reference-point -S <bw_1> ... -R <gtf-derived TSS BED> -a 3000 -b 3000` → `plotHeatmap`. Skipped when no GTF.
- **Peak heatmap** — `computeMatrix reference-point -S <bw_1> ... -R consensus_peaks.bed -a 1500 -b 1500` → `plotHeatmap`. Centered on peak midpoints.
- **PCA** — DESeq2 `vst` on `peak_counts.txt`, then `prcomp` on top-variable peaks. Scatter coloured by condition; CSV of PC loadings.
- **Sample correlation** — Pearson on VST-normalised counts; clustered heatmap.
- **IDR** (opt-in) — per condition: BAM → namesort → split into two pseudo-replicates → MACS2 each → `idr --rank p.value` against each replicate pair and pooled. ENCODE thresholds: ≥ 70k IDR peaks ideal, ≥ 50k acceptable.

## Demo

This skill has NO `--demo` flag. Smoke-test by running the full chain:

```bash
python skills/epigenomics/bulkatac/bulkatac-preprocessing/bulkatac-preprocessing.py --demo --wd /tmp/atac
python skills/epigenomics/bulkatac/bulkatac-mapping/bulkatac-mapping.py            --wd /tmp/atac
python skills/epigenomics/bulkatac/bulkatac-peak-calling/bulkatac-peak-calling.py  --wd /tmp/atac
```

## Dependencies

**Python packages** (declared in SKILL.md `requires`):

- `pandas` — DataFrame assembly for summary CSVs.
- `numpy` — transitive (pandas).

**External tools** (must be on `PATH`):

- `macs2` (≥ 2.2 — supports `--format BAMPE`)
- `samtools` (for pool / namesort / split for IDR)
- `bedtools` (≥ 2.30 — for `merge`, `intersect`, `closest`)
- `featureCounts` (Subread package; ≥ 2.0 — supports `--countReadPairs`)
- `deeptools` (`computeMatrix`, `plotHeatmap`, `plotPCA`, `plotCorrelation`)
- `annotatePeaks.pl` (HOMER; optional — bedtools fallback when absent)
- `idr` (optional; only required with `--idr`)

## References

- Zhang Y, et al. (2008). Model-based Analysis of ChIP-Seq (MACS).
  *Genome Biology* 9:R137. <https://doi.org/10.1186/gb-2008-9-9-r137>
- Quinlan AR, Hall IM (2010). BEDTools: a flexible suite of utilities for
  comparing genomic features. *Bioinformatics* 26:841–842.
  <https://doi.org/10.1093/bioinformatics/btq033>
- Liao Y, Smyth GK, Shi W (2014). featureCounts: an efficient general-purpose
  program for assigning sequence reads to genomic features. *Bioinformatics*
  30:923–930. <https://doi.org/10.1093/bioinformatics/btt656>
- Heinz S, et al. (2010). Simple combinations of lineage-determining
  transcription factors prime cis-regulatory elements (HOMER). *Mol. Cell*
  38:576–589. <https://doi.org/10.1016/j.molcel.2010.05.004>
- Li Q, Brown JB, Huang H, Bickel PJ (2011). Measuring reproducibility of
  high-throughput experiments (IDR). *Ann. Appl. Stat.* 5:1752–1779.
  <https://doi.org/10.1214/11-AOAS466>
- Ramírez F, et al. (2016). deepTools2. *Nucleic Acids Res.* 44:W160–W165.
  <https://doi.org/10.1093/nar/gkw257>
- ENCODE ATAC-seq pipeline — <https://www.encodeproject.org/atac-seq/> —
  naive-overlap consensus, FRiP and IDR peak-count thresholds.
- CebolaLab ATAC-seq — <https://github.com/CebolaLab/ATAC-seq>
