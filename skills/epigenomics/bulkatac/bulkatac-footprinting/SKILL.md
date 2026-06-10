---
name: bulkatac-footprinting
description: Load when running TF footprint analysis on bulk ATAC-seq via TOBIAS (Bentsen 2020) — Tn5 bias correction, per-base footprint scores, motif scanning, bound/unbound classification, and differential TF binding between two conditions. Skip for scATAC, ChIP-seq, or before consensus peaks are called (run bulkatac-peak-calling first).
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- atac-seq
- footprinting
- tobias
- tf-binding
- jaspar
- atacorrect
- bindetect
- motif-scanning
requires:
- pandas
- numpy
---

## When to use

The user has consensus peaks + dedup BAMs from `bulkatac-peak-calling` and wants nucleotide-resolution TF footprinting: TOBIAS `ATACorrect` removes Tn5 sequence bias, `ScoreBigwig` derives per-base footprint scores, `BINDetect` scans motifs and classifies each TFBS as bound/unbound, and (with ≥ 2 conditions) ranks TFs by differential binding change. Statistical power comes from per-TFBS spatial testing — no biological replicates required. Skip for scATAC, ChIP-seq, or to start from FASTQs / BAMs — run the preprocessing → mapping → peak-calling chain first.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-3 result | `<project>/peak_calling/result.json` from `bulkatac-peak-calling` | Yes (via `--prev-result`, or sibling-detected from `--wd`); must carry the `mapping` chain so BAM paths resolve |
| Genome FASTA | `.fa` (+ `.fai` auto-built) | Auto-detected from Step 2's `reference_<genome>/` dir; pass `--genome-fasta` to override |
| Motif database | JASPAR / PFM / MEME format | Auto-downloaded from JASPAR 2024 by organism group if `--motifs` is omitted (network required first run) |
| Blacklist BED | ENCODE blacklist | Auto-detected from Step 2; optional |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Per-condition ATACorrect + footprint paths, BINDetect summary, aggregate-plot count, normalisation table |
| Result envelope | `<output>/result.json` | `footprinting` block with `conditions`, `atacorrect`, `footprints`, `bindetect`, `aggregate_plots`, `top_tf_ranking` |
| Merged BAMs | `<output>/merged_bams/<condition>.bam` | One per condition (replicates merged via `samtools merge`) |
| Merged peaks | `<output>/merged_peaks.bed` | Consensus peaks staged for TOBIAS |
| Bias-corrected signal | `<output>/atacorrect/<condition>/` | `corrected.bw`, `uncorrected.bw`, `bias.bw`, QC PDF |
| Footprint scores | `<output>/footprints/<condition>/` | Per-base footprint score BigWig |
| Motif scan + binding | `<output>/bindetect/` | `bindetect_results.txt` (one row per TF), `bindetect_figures.pdf`, per-TF bound/unbound BEDs |
| TF ranking | `<output>/top_tf_ranking.tsv` | Top-TF ranking by binding score / differential change |
| Aggregate plots | `<output>/plots/aggregate/` | Aggregate footprint profiles for top TFs |
| Differential volcano | `<output>/plots/tf_differential_volcano.{pdf,png}` | Only when ≥ 2 conditions |
| JASPAR cache | `<output>/motifs/JASPAR2024_CORE_<group>.jaspar` | Only when `--motifs` was auto-downloaded |
| Reproducibility | `<output>/reproducibility/commands.sh` | Re-run command |

## Flow

1. Check prerequisites — `samtools` + `bedtools` must be on `PATH`; hard-fail with install hint if either is missing. TOBIAS is NOT a PATH prerequisite — it runs in the isolated `omicsclaw_tobias` sub-env, auto-provisioned on first use (`bulkatac-footprinting.py:504-512`).
2. Locate the upstream Step-3 `result.json`: use `--prev-result`, otherwise the sibling `<project>/peak_calling/result.json` (`--wd`'s parent) (`bulkatac-footprinting.py:514-523`).
3. Reconstruct consensus BED + sample BAMs + sample→condition mapping; walk the `prev_result` chain back to Step 2 if Step 3 didn't carry mapping (`bulkatac-footprinting.py:227-274`).
4. Resolve genome FASTA — CLI `--genome-fasta` overrides; otherwise search `genome_files.fasta`, Step-2 `ref_dir`, and any `reference_<genome>*` sibling dirs (`bulkatac-footprinting.py:191-224`).
5. Build `.fai` via `samtools faidx` if absent (`bulkatac-footprinting.py:556-562`).
6. Resolve motif database — CLI `--motifs` overrides; otherwise auto-download the matching JASPAR 2024 CORE set (vertebrates / plants / insects / fungi / nematodes) by genome-name mapping (`bulkatac-footprinting.py:144-184`).
7. Run the TOBIAS pipeline via `_lib.footprinting.run_footprinting` — merge BAMs per condition → ATACorrect → ScoreBigwig → BINDetect → PlotAggregate (`bulkatac-footprinting.py:606-619`).
8. Write `report.md`, `result.json`, `reproducibility/`, `README.md`, then stdout summary (`bulkatac-footprinting.py:621-657`).

## Gotchas

- **No `--demo` flag.** `bulkatac-footprinting.py:498` jumps straight to prerequisite checks + Step-3 loading. Smoke-test by running the full Step 1 → 2 → 3 chain with `--demo`, then this script with the same `--wd`.
- **Chains via `--prev-result` (also accepts `--input` as an alias).** `bulkatac-footprinting.py:439-443` reads the upstream skill's `result.json`; BAM paths come from the carried `mapping` chain. `--wd` is aliased to `--output` (`bulkatac-footprinting.py:446`) so the OmicsClaw runner's `--output <path>` + `--input <result.json>` injection works. If your Step-3 result was generated before the mapping-chain change, re-run peak-calling to refresh `result.json`.
- **JASPAR motif download hits the network on first run.** When `--motifs` is omitted, `bulkatac-footprinting.py:155-184` URL-retrieves the matching CORE set from `jaspar.elixir.no`. ~1-3 MB; cached in `motifs/` for re-runs. Provide `--motifs /path/to/local.jaspar` for offline / proxied environments.
- **Unknown genomes default to JASPAR vertebrates.** `bulkatac-footprinting.py:152` falls back to `vertebrates` when neither `_GENOME_TO_JASPAR` nor `_GENOME_PREFIX_TO_JASPAR` matches. On exotic-organism runs this silently mis-routes motifs — pass `--motifs` explicitly.
- **BAMs must NOT be Tn5-shifted upstream.** TOBIAS ATACorrect applies the +4/-5 offset and corrects Tn5 sequence bias internally; pre-shifted BAMs would double-correct. `bulkatac-mapping`'s BAMs are unshifted by design — see that skill's gotcha.
- **BINDetect needs no biological replicates.** Per the docstring at `bulkatac-footprinting.py:14-18`, the spatial test compares each TFBS log2FC to ~100 random genomic-background log2FCs; a TF with 1000 sites is well-powered even from a single replicate per condition. Replicate-aware DA still requires `bulkatac-da` on peak counts.
- **`--treat` / `--control` only set BINDetect ordering.** The flags don't affect significance — they control which condition is the numerator in the log2 binding-change. Omit them and BINDetect picks alphabetically (consistent with `bulkatac-da`'s auto-contrast).
- **Differential analysis silently degrades to single-condition mode with < 2 conditions.** `result.json["footprinting"]["bindetect"]["is_differential"]` is `false` and the volcano plot is not emitted; per-TF binding scores still come out via `bindetect_results.txt`. Check this field before assuming the run was a contrast.

## Key CLI

End-to-end run after `bulkatac-peak-calling` (auto-detects everything, downloads JASPAR):

```bash
python skills/epigenomics/bulkatac/bulkatac-footprinting/bulkatac-footprinting.py \
    --wd ./atac_run --threads 32
```

Explicit motif database + contrast ordering:

```bash
python skills/epigenomics/bulkatac/bulkatac-footprinting/bulkatac-footprinting.py \
    --wd ./atac_run \
    --motifs /refs/motifs/JASPAR2024_CORE_vertebrates.jaspar \
    --treat T15 --control T0 --threads 48
```

Offline run with all paths pre-staged:

```bash
python skills/epigenomics/bulkatac/bulkatac-footprinting/bulkatac-footprinting.py \
    --prev-result /tmp/atac/peak_calling/result.json \
    --wd /tmp/atac \
    --genome-fasta /refs/hg38/hg38.fa \
    --motifs /refs/motifs/JASPAR2024_CORE_vertebrates.jaspar \
    --blacklist /refs/hg38/ENCFF356LFX.bed.gz \
    --threads 48
```

## See also

- `references/parameters.md` — every CLI flag with type + default (auto-generated from `parameters.yaml`).
- `references/methodology.md` — TOBIAS sub-step details (ATACorrect normalisation = `10M / reads_in_peaks`; BINDetect quantile normalisation + spatial test against 100 background resamples), JASPAR organism-group mapping table, BAM-merge convention.
- `references/output_contract.md` — full output tree, `bindetect_results.txt` column schema, `top_tf_ranking.tsv` schema, `result.json["footprinting"]` keys.
- Adjacent skills:
  - Upstream — `bulkatac-peak-calling` (must run first to produce consensus peaks + carry the BAM chain).
  - Parallel — `bulkatac-motif-enrichment` (HOMER motif over-representation in peak sets — different question: where do motifs accumulate vs which are actively bound).
  - Downstream — none yet (`bulkatac-da` consumes peak counts independently; integrating per-TF binding changes with DA peaks is a manual analysis).
