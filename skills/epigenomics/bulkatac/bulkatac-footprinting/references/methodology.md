# Methodology — bulkatac-footprinting

## Capabilities

Bulk ATAC-seq ENCODE Step 5b — TF footprint analysis via the TOBIAS
toolkit (Bentsen et al. 2020, *Nat Commun* 11:4267). Concretely:

- **Tn5 bias correction** — TOBIAS `ATACorrect` learns the per-position Tn5 insertion-sequence bias from the genome FASTA and subtracts it from the per-condition pileup.
- **Per-base footprint scoring** — TOBIAS `ScoreBigwig` derives footprint scores from the corrected signal (positive scores at protein-protection footprints; negative at the flanking accessible cuts).
- **Motif scanning + binding classification** — TOBIAS `BINDetect` scans the motif database across the consensus peak set, scores each TFBS, and classifies it as bound / unbound per condition.
- **Differential TF binding** (≥ 2 conditions) — `BINDetect` computes per-TF log2 binding-change and a one-sample t-test against ~100 random genomic-background log2FCs; no biological replicates required because per-TFBS observations carry the statistical power.
- **Aggregate footprint profiles** — `PlotAggregate` for the top 20 TFs by binding score / differential change.
- **JASPAR auto-resolution** — when `--motifs` is omitted, downloads the JASPAR 2024 CORE non-redundant set matching the genome's organism group (vertebrates / plants / insects / fungi / nematodes).

What this skill does NOT do (handed off elsewhere):

- Replicate-aware DA on peak counts → `bulkatac-da` (DESeq2 on `peak_counts.txt`).
- HOMER motif over-representation in peak sets → `bulkatac-motif-enrichment` (different question: where do motifs accumulate, not which are bound).
- Integration of TF binding-change with DA peaks → manual analysis at this stage; no integration skill yet.

## Workflow

1. **Prerequisites** — `check_prerequisites` exits if samtools / bedtools are missing. TOBIAS is NOT checked here — it runs in the isolated `omicsclaw_tobias` sub-env (auto-provisioned by `_ensure_tobias_env()`), not on the current PATH.
2. **Locate Step-3 result** — `--prev-result` explicit, else `<wd>/peak_calling/result.json`. The mapping chain must be present so BAM paths resolve; the script walks `prev_result` back to Step 2 if Step 3 didn't carry it.
3. **Reconstruct upstream state** — consensus BED, sample BAMs, sample→condition map, genome FASTA candidates, blacklist.
4. **Resolve genome FASTA** — CLI override → `genome_files.fasta` → Step-2 `ref_dir` → `reference_<genome>*` sibling glob. Hard-fail if none found.
5. **Build `.fai`** — `samtools faidx` if missing.
6. **Resolve motif database** — CLI override → JASPAR auto-download by organism group → fallback `vertebrates`. Cached under `motifs/`.
7. **Resolve blacklist** — CLI override → Step-2 detected → none.
8. **Run TOBIAS pipeline** — `_lib.footprinting.run_footprinting` merges BAMs per condition (`<cond>_merged.bam`), then ATACorrect → ScoreBigwig → BINDetect → PlotAggregate.
9. **Emit outputs** — `report.md`, `result.json`, `reproducibility/`, `README.md`, then stdout summary.

## Methodology — per-step details

### Per-condition BAM merging

ATACorrect / ScoreBigwig take a single BAM per condition. The wrapper
merges all replicates of a condition via `samtools merge` into
`merged_bams/<cond>_merged.bam`. Indexed in place. Replicates are
treated as equivalent biological observations — no per-replicate weighting.

### ATACorrect (Tn5 bias correction)

`TOBIAS ATACorrect` learns the per-position 12-mer insertion bias from
the genome sequence around observed cut sites and removes it from the
signal:

- **Input**: merged BAM + genome FASTA + consensus peaks (`--peaks`) + (optional) blacklist (`--blacklist`).
- **Normalisation**: signal at peaks is scaled to `10M / reads_in_peaks` so depth differences between conditions don't dominate.
- **Outputs** (per condition): `<prefix>_uncorrected.bw`, `<prefix>_bias.bw`, `<prefix>_expected.bw`, `<prefix>_corrected.bw`, plus a multi-page QC PDF.

The corrected BigWig is the canonical signal used by ScoreBigwig and
PlotAggregate downstream.

### ScoreBigwig (per-base footprint scoring)

Slides over the corrected signal and computes a footprint score per
base — high values mark a protected window (likely TF occupancy) with
flanking accessibility. Output: `<cond>_footprints.bw` per condition.

### BINDetect (motif scanning + binding classification + differential analysis)

- **Motif scan**: PWMs from the JASPAR database are scanned across the merged consensus peaks → one BED of putative TFBSs per TF per condition.
- **Footprint score per TFBS**: aggregated from the per-base footprint BigWig.
- **Bound / unbound classification**: per-TF threshold derived from the bimodal distribution of footprint scores. `<TF>_<cond>_bound.bed` and `<TF>_<cond>_unbound.bed` per condition.
- **Differential analysis** (≥ 2 conditions): per TF, the log2 binding-change between conditions is computed. A one-sample t-test compares this change to a null distribution of ~100 random-genomic-background log2FCs. The p-value reflects how anomalous the TF's binding shift is vs. the background — *not* how reproducible it is across biological replicates.
- **Normalisation**: BINDetect applies a quantile normalisation (sigmoid-fitted, non-linear) on the per-condition footprint scores before differential testing, so absolute-scale differences between conditions don't bias the contrast.

`is_differential = true` in `result.json` iff ≥ 2 conditions were
detected; the differential change / pvalue columns in
`bindetect_results.txt` exist only in that case.

### PlotAggregate (top-TF aggregate footprints)

For the top N TFs (default N=20; `_lib/footprinting.py:752-754`), an
aggregate footprint profile is rendered — mean corrected-signal
intensity around all bound TFBSs, with the motif location overlaid.
The TFs are ranked by binding score (single condition) or differential
change (≥ 2 conditions).

### JASPAR organism-group mapping

When `--motifs` is omitted the genome name is mapped to a JASPAR
organism group via `_GENOME_TO_JASPAR` and `_GENOME_PREFIX_TO_JASPAR`
(`bulkatac-footprinting.py:122-141`):

| Group | Matched genomes / prefixes |
|---|---|
| vertebrates | hg38, hg19, mm10, mm39, rn6, rn7, danRer11, danRer10, galGal6; prefixes `hg`, `mm`, `rn`, `danrer`, `galgal` |
| insects | dm6, dm3; prefix `dm` |
| nematodes | ce11, ce10; prefixes `ce`, `caeel` |
| fungi | sacCer3, sacCer2; prefix `saccer` |
| plants | TAIR10; prefixes `tair`, `oryza` |
| vertebrates (fallback) | anything that matches nothing else |

The vertebrates fallback at `bulkatac-footprinting.py:152` means unknown
genomes silently route to the wrong motif set; pass `--motifs` for
exotic organisms.

## Demo

This skill has NO `--demo` flag. Smoke-test via the full chain (sacCer3
yeast demo dataset routes to JASPAR fungi motifs):

```bash
WD=/tmp/atac-demo
python skills/epigenomics/bulkatac/bulkatac-preprocessing/bulkatac-preprocessing.py --demo --wd $WD
python skills/epigenomics/bulkatac/bulkatac-mapping/bulkatac-mapping.py            --wd $WD
python skills/epigenomics/bulkatac/bulkatac-peak-calling/bulkatac-peak-calling.py  --wd $WD
python skills/epigenomics/bulkatac/bulkatac-footprinting/bulkatac-footprinting.py  --wd $WD
```

## Dependencies

**Python packages** (declared in SKILL.md `requires`):

- `pandas`, `numpy` — table I/O + summary aggregation.

**External Python packages** (must be importable; not declared in
`requires` because they're TOBIAS's responsibility):

- `tobias` — provides the `TOBIAS` CLI with `ATACorrect`, `ScoreBigwig`, `BINDetect`, `PlotAggregate` sub-commands.

**External tools on the current PATH** (hard-checked by
`check_prerequisites`):

- `samtools` (≥ 1.10 — for merge, index, faidx)
- `bedtools` (≥ 2.30)

**TOBIAS** is NOT on the current PATH — it runs in the dedicated
`omicsclaw_tobias` conda sub-env (`tobias>=0.17`, `pandas<2`).
`check_tobias()` reports its version from that sub-env; `_ensure_tobias_env()`
auto-creates the env on first use if it does not already exist.

**Tested versions**: TOBIAS ≥ 0.16. Genome reference: any FASTA with a
working `.fai` (auto-built).

## References

- Bentsen M, et al. (2020). ATAC-seq footprinting unravels kinetics of
  transcription factor binding during zygotic genome activation (TOBIAS).
  *Nat. Commun.* 11:4267. <https://doi.org/10.1038/s41467-020-18035-1>
- TOBIAS — <https://github.com/loosolab/TOBIAS>
- Rauluseviciute I, et al. (2024). JASPAR 2024: 20th anniversary of the
  open-access database of transcription factor binding profiles.
  *Nucleic Acids Res.* 52:D174–D182. <https://doi.org/10.1093/nar/gkad1059>
- ENCODE ATAC-seq pipeline — <https://www.encodeproject.org/atac-seq/>
