# Methodology — bulkchip-preprocessing

> Status: implemented (FastQC + fastp/Trim Galore + working `--demo`).

## Capabilities

- Parse + validate a ChIP-seq sample sheet, including **ChIP↔input/IgG control
  pairing** (the defining ChIP-seq preprocessing concern).
- FastQC read quality reports (optional).
- Adapter + quality trimming with fastp (default) or Trim Galore.

It does **not** align (that is `bulkchip-mapping`) or call peaks.

## Workflow

1. **Sample sheet** (`_lib.preprocessing.get_data`)
   - Columns: `sample, condition, replicate, R1 [, R2], control, antibody [, peak_mode]`.
   - Control/input samples have `is_control=true` (or empty `antibody`).
   - Build `control_map = {chip_sample → control_sample}`; **fail fast** if a
     ChIP sample names a control that is absent from the sheet.
   - Layout (paired vs single end) inferred from presence of `R2`.
2. **FastQC** (optional) — one report per FASTQ.
3. **Trimming** (`run_all_preprocessing`)
   - fastp (default) or Trim Galore, chosen by `--tool` (`auto` → fastp).
   - Adapter: Illumina universal `AGATCGGAAGAGC` (TruSeq), overridable via `--adapter`.
   - `--quality` (default 20), `--min-length` (default 20).

## Method notes

- **Why Illumina universal, not Nextera**: ChIP libraries are typically TruSeq,
  unlike ATAC's Tn5/Nextera chemistry — hence a different default adapter from
  `bulkatac-preprocessing`.
- **ENCODE read-length standard**: 25 bp processable, ≥50 bp recommended
  (`encode_qc_criteria.ENCODE_QC_THRESHOLDS["min_read_length_bp"]`).
- **fastp vs Trim Galore**: fastp is faster and emits JSON QC; Trim Galore wraps
  Cutadapt + FastQC and is the common ENCODE-adjacent choice — pick per lab
  convention.

## Demo

`--demo` fetches the **nf-core SPT5 ChIP-seq test set** (*S. cerevisiae*): SPT5
ChIP at two timepoints (T0 / T15) × 2 replicates + 2 input controls, paired-end,
sacCer3. ChIP reads come from the nf-core ATAC-seq yeast test FASTQs
(SRR18221xx); inputs from the chipseq test FASTQs (SRR520480x, ss100k). Files
download to `<output>/../fastq/` (GitHub primary, EBI ENA fallback), are
subsampled to `--demo-n-reads` (default 50k), and a `demo_samplesheet.tsv`
(with `control`/`antibody`/`peak_mode` columns) is written beside the output.
Requires the `omicsclaw_bulkchip` env (`bash 0_setup_env_for_bulkchip.sh`).

## Dependencies

- Python: pandas, numpy
- External: FastQC, fastp, Trim Galore (see `0_setup_env_for_bulkchip.sh`)

## References

- ENCODE ChIP-seq standards — https://www.encodeproject.org/chip-seq/transcription_factor/
- nf-core/chipseq — https://github.com/nf-core/chipseq
- Churros — https://churros.readthedocs.io/
- fastp — https://github.com/OpenGene/fastp
- Trim Galore — https://github.com/FelixKrueger/TrimGalore
