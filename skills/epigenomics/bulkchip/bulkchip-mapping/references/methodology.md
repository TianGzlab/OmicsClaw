# Methodology — bulkchip-mapping

> Scaffold: methodology specified; tool-backed implementation pending.

## Capabilities

- Align ChIP + control FASTQs; ENCODE BAM filtering + dedup; NRF/PBC1/PBC2.
- ChIP signal-to-noise QC: strand cross-correlation (NSC/RSC) + deepTools
  fingerprint; RPGC bigWig tracks.

Does **not** call peaks (`bulkchip-peak-calling`) or annotate.

## Workflow

1. **Reference** (`_lib.mapping.prepare_reference`) — FASTA + aligner index
   (+ blacklist) for the build, or use a supplied index.
2. **Alignment** (`run_all_mapping`)
   - BWA-MEM2 (default): `bwa-mem2 mem` — a drop-in, faster reimplementation of
     BWA-MEM with identical output (ENCODE ChIP-seq / nf-core/chipseq workhorse).
     `bwa` (classic BWA-MEM) is the low-RAM fallback; Bowtie2
     (`--very-sensitive --no-mixed --no-discordant -X 700` PE) is also available.
   - ENCODE BAM filter: `samtools view -F 1804 -f 2 -q 30` (PE) / `-F 1796 -q 30`
     (SE); MAPQ ≥ 30 removes multi-mappers.
   - Dedup: `samtools markdup -r`. Optional ENCODE blacklist removal.
   - **Controls aligned identically** and carried forward.
3. **Library complexity** — NRF = Distinct/Total; PBC1 = OneRead/Distinct;
   PBC2 = OneRead/TwoRead (ENCODE ChIP bar PBC2 > 10).
4. **ChIP QC** (`run_all_qc_after_mapping`)
   - **Cross-correlation** (phantompeakqualtools `run_spp.R` / `ssp`):
     NSC = fragment-CC / min-CC; RSC = (frag-CC − min-CC)/(phantom-CC − min-CC).
     Also yields the predominant fragment-length estimate.
   - **Fingerprint** (`deeptools plotFingerprint`): cumulative read-coverage
     curve, ChIP vs matched input; reports JS distance / elbow.
   - **bigWig**: `bamCoverage` RPGC, `--ignoreDuplicates --minMappingQuality 30`
     (per-sample 1× track).
   - **log2(ChIP/input) bigWig**: `bamCompare --operation log2
     --scaleFactorsMethod readCount` — depth-scales ChIP vs its matched input
     and writes the per-bin log2 ratio, subtracting input background that the
     per-sample RPGC track cannot.

## ENCODE thresholds (`_lib.encode_qc_criteria`)

| Metric | Preferred | Acceptable |
|---|---|---|
| NRF | > 0.90 | > 0.80 |
| PBC1 | > 0.90 | > 0.50 |
| PBC2 | > 10 | > 3 |
| NSC | > 1.10 | > 1.05 |
| RSC | > 1.00 | > 0.80 |
| Align rate | > 95% | > 80% |
| Usable reads (TF/narrow) | ≥ 20 M | ≥ 10 M |
| Usable reads (broad histone) | ≥ 45 M | ≥ 20 M † |

NRF/PBC1/PBC2 preferred bars and the 20 M (narrow) / 45 M (broad) usable-read
targets are quoted from the ENCODE TF and histone standards pages; NSC/RSC bars
are the phantompeakqualtools / Landt 2012 critical thresholds (NSC 1.1, RSC 1.0;
low < 1.05 / < 0.8). † The broad "acceptable" 20 M is an interpolated soft floor,
not an explicit ENCODE broad cutoff (ENCODE states a single 45 M broad target).

## Demo

No implemented demo dataset yet (scaffold).

## Dependencies

- Python: pandas, numpy
- External: bwa-mem2 / bwa / bowtie2, samtools, deeptools, bedtools,
  phantompeakqualtools (`run_spp.R`) or ssp (see `0_setup_env_for_bulkchip.sh`)

## References

- ENCODE TF ChIP-seq standards — https://www.encodeproject.org/chip-seq/transcription_factor/
- ENCODE histone ChIP-seq standards — https://www.encodeproject.org/chip-seq/histone/
- Landt et al. 2012 (ENCODE/modENCODE) — https://doi.org/10.1101/gr.136184.111
- phantompeakqualtools — https://github.com/kundajelab/phantompeakqualtools
- SSP (strand-shift profile, NSC/RSC alternative to run_spp.R) — https://github.com/rnakato/SSP
- deepTools — https://github.com/deeptools/deepTools
- nf-core/chipseq — https://github.com/nf-core/chipseq
- Churros (Docker-based ChIP-seq/ATAC/CUT&TAG pipeline; Wang & Nakato, DNA Research 2024) — https://churros.readthedocs.io/en/latest/ ; https://doi.org/10.1093/dnares/dsad026
- bwa-mem2 — https://github.com/bwa-mem2/bwa-mem2
