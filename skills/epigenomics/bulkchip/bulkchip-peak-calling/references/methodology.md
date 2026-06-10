# Methodology — bulkchip-peak-calling

> Implemented (MACS2-backed). See `_lib/peak_calling.py`.

## Capabilities

- MACS2 peak calling **against the matched input/IgG control**, narrow or broad.
- ENCODE naive-overlap consensus across conditions (vs pooled control).
- featureCounts peak × sample matrix; FRiP; optional IDR.

Stops at the count matrix + FRiP — annotation/enrichment, motifs, and
differential binding live in sibling skills.

## Workflow

1. **Pairing** — reconstruct ChIP↔control BAM pairs from Step 2's `control_map`.
2. **Peak mode** — `--peak-mode auto` infers per-sample from the antibody label
   (`infer_peak_mode`): broad histone marks → broad, else narrow. `narrow`/
   `broad` force globally.
3. **MACS2** (`run_all_peak_calling`)
   - Narrow: `macs2 callpeak -t <chip> -c <control> -g <eff_genome> -q <qvalue>
     --keep-dup all` (BAMs already deduped) → narrowPeak + summits.
   - Broad: add `--broad --broad-cutoff <c>` → broadPeak (no summits).
   - Effective genome size from build name (FASTA fallback).
4. **Consensus** (`build_consensus_peaks`, ENCODE naive overlap)
   - Per condition: pool replicate ChIP BAMs → re-call MACS2 vs pooled control →
     intersect pooled peaks with each replicate at `--overlap-fraction`
     reciprocal overlap → reproducible set.
   - Across conditions: `cat | sort | bedtools merge` → `consensus_peaks.bed` →
     SAF.
5. **Count matrix** — `featureCounts -F SAF` on the consensus (PE:
   `-p --countReadPairs`) → raw counts for `bulkchip-DA`.
6. **FRiP** — fraction of usable reads in called peaks, per sample.
7. **IDR** (optional, `--idr`) — point-source only; pseudo-replicate + true-rep
   IDR per condition; rescue / self-consistency ratios < 2 to pass.

## Method notes

- **Why a control is mandatory**: ENCODE requires a matched input/IgG of equal
  run type + read length; MACS2 uses it to model local background (lambda),
  suppressing open-chromatin / copy-number artifacts.
- **Narrow vs broad**: point-source factors (TFs) and sharp marks give crisp
  summits (narrow); spreading marks (H3K9me3/H3K27me3/H3K36me3) need broad
  region merging.
- **`--keep-dup all`**: duplicates were removed in Step 2; MACS2 must not
  double-filter.

## Demo

No implemented demo dataset yet (scaffold).

## Dependencies

- Python: pandas, numpy
- External: macs2, bedtools, featureCounts (subread), idr
  (see `0_setup_env_for_bulkchip.sh`)

## References

- ENCODE ChIP-seq standards — https://www.encodeproject.org/chip-seq/transcription_factor/
- MACS2 — https://github.com/macs3-project/MACS
- IDR — https://github.com/nboley/idr
- nf-core/chipseq — https://github.com/nf-core/chipseq
