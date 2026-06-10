# Methodology — bulkatac-preprocessing

## Capabilities

Bulk ATAC-seq preprocessing covering ENCODE Step 1 (data loading + QC) and
Step 2 of the Step-1 pipeline (adapter trimming). Specifically:

- **Sample-sheet ingestion** — TSV/CSV with `sample, condition, replicate, R1[, R2]`. Single-end and paired-end auto-detected from presence/absence of the `R2` column. Multi-condition and arbitrary replicate counts supported; the sheet must have at least one row.
- **Optional FastQC** — runs per-FASTQ when `fastqc` is in `PATH` (skip with `--no-fastqc`). HTML + summary written next to each trimmed FASTQ.
- **Adapter trimming** — picks `fastp` (preferred) or `Trim Galore` based on `--tool` (`auto` resolves to fastp when available). Nextera adapter `CTGTCTCTTATACACATCT` is the default; override with `--adapter`.
- **Demo mode** — fetches GSE66386 (*S. cerevisiae* osmotic-stress T0 vs T15, paired-end, sacCer3), subsamples to `--demo-n-reads` per FASTQ, then runs the full pipeline.

What this skill explicitly does NOT do (yet — handled by sibling skills):

- Alignment / BAM filtering / dedup → `bulkatac-mapping`
- Post-alignment QC (NRF/PBC, TSS enrichment, fragment-length) → `bulkatac-mapping`
- Peak calling / FRiP / IDR → `bulkatac-peak-calling`
- Differential accessibility → `bulkatac-da`
- Motif / footprinting → `bulkatac-motif-enrichment`, `bulkatac-footprinting`

## Workflow

1. **Args + validation** — argparse parses CLI, then enforces that one of `--input`/`--demo` is set.
2. **Genome resolution** — in `--demo` mode the genome string is forced to `sacCer3` (with a warning if the user passed something else). Otherwise `--genome` is recorded as-is. The value is metadata only; trimming uses no reference sequence.
3. **Working-dir layout** — `<wd>/` (the `--output`/`--wd` path) *is* the skill's own output namespace; all skill-generated artifacts land directly under it, with no nested `preprocessing/` subdir. Raw demo downloads (`fastq/`, `demo_samplesheet.tsv`) instead land at `<wd>/../` (the parent), beside the output dir — they are demo *input*, kept out of the artifact namespace and shareable across sibling skills.
4. **Step 1a — `get_data`** (`_lib/preprocessing.py`) — loads or downloads the sample sheet, validates required columns, returns a `SampleSheet` object. In demo mode this is where SRA fetch + subsampling happens.
5. **Step 1b — `run_all_preprocessing`** (`_lib/preprocessing.py`) — iterates samples and invokes fastp/Trim Galore. Each sample produces trimmed FASTQ(s), a per-sample stats dict, and (optionally) a FastQC report.
6. **Summary + reproducibility** — `build_preprocessing_summary` aggregates per-sample stats into a single DataFrame written as `trimmed_summary.csv`. `report.md` includes this table inline. `commands.sh` records the exact re-run command (after `--tool auto` is resolved to the actual tool).

## Methodology — per-tool details

### fastp (default when available)

- Multi-threaded by default; honours `--threads`.
- Built-in adapter detection from paired-end overlap; the explicit `--adapter` is still passed to suppress detection guesswork.
- Sliding-window quality trimming: window=4 bp, mean Phred ≥ `--quality` (default Q20).
- Length filter: discards reads shorter than `--min-length` after trimming (default 36 bp — matches the ENCODE ATAC pipeline minimum).
- Output: paired `<sample>_R{1,2}.trimmed.fastq.gz` + `<sample>.fastp.json` + `<sample>.fastp.html`.

### Trim Galore (fallback / opt-in via `--tool trim_galore`)

- Wraps `cutadapt`; thread count is capped to a Trim-Galore-imposed limit (≤8 useful threads regardless of `--threads`).
- Same Nextera adapter; same quality/length cutoffs.
- Output: `<sample>_R{1,2}_val_{1,2}.fq.gz` (Trim-Galore's native naming) renamed to the same `<sample>_R{1,2}.trimmed.fastq.gz` convention by `_lib`.

## Demo dataset

- **Accession**: GSE66386 (SRA: SRP055259)
- **Organism**: *Saccharomyces cerevisiae* (strain BY4742)
- **Conditions**: T0 (baseline) vs T15 (15 min after 1 M sorbitol osmotic stress)
- **Replicates**: 2 per condition (4 samples total)
- **Layout**: paired-end
- **Genome build**: sacCer3 (~12 Mb)
- **Why this dataset**: small genome → quick alignment / peak calling downstream; clear T0/T15 condition contrast for differential accessibility demos; published in Lai et al., 2015 (*Cell Reports*).

Raw FASTQs total ~1 GB before subsampling. `--demo-n-reads` (default 50,000) reads/FASTQ is enough for sane fastp + alignment QC numbers while keeping the demo under one minute.

## Dependencies

**Python packages** (declared in SKILL.md `requires`):

- `pandas` — `build_preprocessing_summary` aggregates per-sample stats.
- `numpy` — transitive (pandas).

**External tools** (must be on `PATH`):

- `fastp` *or* `trim_galore` (one of; `auto` mode requires at least one)
- `fastqc` — optional; skipped silently with a warning if not in PATH
- `fastq-dump` / `prefetch` (`sra-tools`) — only required for `--demo`
- `wget` / `curl` — only required for `--demo`

**Tested versions**: fastp ≥ 0.23, Trim Galore ≥ 0.6, FastQC ≥ 0.11, sra-tools ≥ 3.0.

## References

- Chen S, Zhou Y, Chen Y, Gu J (2018). fastp: an ultra-fast all-in-one FASTQ
  preprocessor. *Bioinformatics* 34:i884–i890.
  <https://doi.org/10.1093/bioinformatics/bty560>
- Krueger F. Trim Galore — a Cutadapt + FastQC wrapper for consistent quality
  and adapter trimming. <https://github.com/FelixKrueger/TrimGalore>
- Andrews S. FastQC: a quality control tool for high-throughput sequence data.
  <https://www.bioinformatics.babraham.ac.uk/projects/fastqc/>
- Buenrostro JD, et al. (2013). Transposition of native chromatin for fast and
  sensitive epigenomic profiling of open chromatin, DNA-binding proteins and
  nucleosome position (ATAC-seq). *Nat. Methods* 10:1213–1218.
  <https://doi.org/10.1038/nmeth.2688>
- ENCODE ATAC-seq pipeline — <https://www.encodeproject.org/atac-seq/>
- Demo data: GEO **GSE66386** — Schep AN, et al. (2015). Structured nucleosome
  fingerprints enable high-resolution mapping of chromatin architecture within
  regulatory regions. *Genome Res.* 25:1757–1770.
  <https://doi.org/10.1101/gr.192294.115>
