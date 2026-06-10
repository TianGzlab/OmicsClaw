# Methodology — bulkhic-preprocessing

> Implemented (fastp + FastQC). See `_lib/preprocessing.py`.

## Capability

First step of the bulk Hi-C suite: load + validate a paired-end Hi-C sample
sheet and run FastQC on raw reads. Adapter/quality trimming (fastp) is OPTIONAL (opt-in via --trim); by default reads are passed through RAW for mapping.

## Sample sheet

Tab- or comma-separated, required columns:

| Column | Meaning |
|---|---|
| `sample` | unique library id |
| `condition` | biological condition (grouping for downstream comparison) |
| `replicate` | integer replicate number |
| `r1`, `r2` | paired FASTQ paths (Hi-C is paired-end) |

Optional: `genome` (per-row build), `adapter_r1`, `adapter_r2`.

Unlike ChIP, there is **no `control` and no `antibody`** column — Hi-C has no
input library.

## Workflow

1. **Load** (`get_data`) — parse the sheet, or in `--demo` mode stream a small
   *D. melanogaster* S2R+ Hi-C test set (Wang et al. 2018, Nat Commun; GSE101317 /
   SRP111713; asynchronous vs G1/S-arrest, SRR5820090/091/092/094; dm6) and write
   `demo_samplesheet.tsv` (2 conditions × 2 replicates). The source FASTQs are
   13–36 GB each, so only the first `--demo-n-reads` pairs (default 3M) are streamed.
2. **FastQC** — raw-read quality report per FASTQ (cached).
3. **fastp** (only with `--trim`; OFF by default) — adapter + quality trim (`--qualified_quality_phred`,
   `--length_required`, `--detect_adapter_for_pe`). Trimming is intentionally
   light: Hi-C mates are mapped *independently* by `bwa mem -SP5M` in Step 2, so
   PE-overlap merging is **not** applied (it would corrupt ligation junctions).

## Method notes

- **Why default no-trim**: Hi-C is mapped raw in the 4DN/distiller/Juicer standard — `bwa-mem2 mem -SP5M` (`-5`) soft-clips adapter/junction tails and `pairtools parse --walks-policy 5unique --max-inter-align-gap` rescues chimeric ligation-junction reads. Pre-alignment trimming is therefore unnecessary; FastQC still runs for QC. Use `--trim` for opt-in light trimming.\n- **Why light trimming (when --trim)**: Hi-C read pairs are chimeric ligation products; the
  two ends are biologically distinct loci. They must be mapped separately, so
  preprocessing only removes sequencing adapters and low-quality tails.
- **Demo dataset**: subsampled Drosophila S2R+ in-situ Hi-C reads (Wang et al.
  2018, GSE101317) map to dm6 — a real metazoan map deep enough for downstream
  TADs/compartments/loops, while dm6 (~143 Mb) keeps reference build + mapping fast.

## Dependencies

- Python: pandas
- CLI: fastp, fastqc (FastQC skipped gracefully if absent)

## References

- 4DN Hi-C processing pipeline — https://data.4dnucleome.org/resources/data-analysis/hi_c-processing-pipeline
- fastp — https://github.com/OpenGene/fastp
