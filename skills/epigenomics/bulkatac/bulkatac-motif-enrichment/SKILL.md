---
name: bulkatac-motif-enrichment
description: Load when running HOMER findMotifsGenome.pl for TF motif enrichment + de novo discovery on bulk ATAC-seq consensus peaks and DA up / down subsets, with per-subset background strategies. Skip for scATAC, ChIP-seq, or before differential accessibility is computed (run bulkatac-DA first).
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- atac-seq
- motif-enrichment
- motif-discovery
- homer
- transcription-factor
- denovo
- background-correction
requires:
- pandas
- numpy
- matplotlib
---

## When to use

The user has DA results from `bulkatac-DA` (which carries the upstream consensus peaks) and wants HOMER motif enrichment on (a) the full consensus peak set against a GC-matched genomic background, plus (b) the DA-up and DA-down subsets against the consensus as background (`-bg -chopify`) so condition-specific TFs are surfaced rather than generic open-chromatin motifs. Each peak set gets both known-motif enrichment and de novo motif discovery. Skip for scATAC, ChIP-seq, or to start before DA is computed — run `bulkatac-DA` first.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-4 (DA) result | `<project>/DA/result.json` from `bulkatac-DA` | Yes (via `--prev-result`, or sibling-detected from `--wd`); script walks `prev_result` back to peak-calling for the consensus BED |
| HOMER genome install | Per `configureHomer.pl -install <genome>` | Required unless `--genome-fasta` is supplied (HOMER's `-fasta` flag bypasses the install) |
| Genome FASTA | `.fa` | Optional — pass `--genome-fasta` to skip the HOMER genome install |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Per-peak-set tables: top 10 known motifs + top 5 de novo motifs + background-strategy explainer |
| Result envelope | `<output>/result.json` | `motif_enrichment` array — one entry per peak set with `n_peaks`, `homer_succeeded`, top motifs, output paths |
| Combined summary | `<output>/top_motif_summary.tsv` | Cross-peak-set ranked motif table |
| HOMER outputs | `<output>/{all_peaks,da_up,da_down}/` | Native HOMER outputs: `knownResults.txt`, `knownResults.html`, `homerResults.html`, `homerMotifs.all.motifs`, plus `knownResults/` + `homerResults/` motif-logo subdirs |
| Plots | `<output>/plots/` | `top_known_motifs_<set>.{pdf,png}`, `top_denovo_motifs_<set>.{pdf,png}` |
| Reproducibility | `<output>/reproducibility/{commands.sh,environment.txt}` | Re-run command + Python pins |

## Flow

1. Check `HOMER findMotifsGenome.pl` is on `PATH`; hard-fail with install hint if absent (`bulkatac-motif-enrichment.py:485-492`).
2. Locate the upstream Step-4 `result.json`: use `--prev-result`, otherwise the sibling `<project>/DA/result.json` (`--wd`'s parent) (`bulkatac-motif-enrichment.py:494-503`).
3. **Hard-check** that the upstream is a DA result — `prev_skill == "bulkatac-DA"` OR a `da` key exists (`bulkatac-motif-enrichment.py:509-513`).
4. Walk the chain back: read DA's `prev_result` key to find the peak-calling `result.json` — hard-fail if missing (`bulkatac-motif-enrichment.py:515-523`).
5. Load consensus BED + genome string + genome FASTA via Step-3 multi-fallback search (`bulkatac-motif-enrichment.py:525-551`).
6. Pick up DA up / down BEDs from the Step-4 envelope (silently skip those peak sets if absent) (`bulkatac-motif-enrichment.py:553-562`).
7. Resolve effective `mask` (`args.mask and not args.no_mask`) and `size` (int, or the literal `"given"`) (`bulkatac-motif-enrichment.py:568-574`).
8. Run HOMER per peak set via `_lib.motif_enrichment.run_motif_enrichment_multi`: `all_peaks` (genomic background), `da_up` (consensus background + `-chopify`), `da_down` (consensus background + `-chopify`) (`bulkatac-motif-enrichment.py:590-602`).
9. Build summary TSV, render top-motif plots, write `report.md` + `result.json` + `reproducibility/` + `README.md`, then stdout summary (`bulkatac-motif-enrichment.py:604-660`).

## Gotchas

- **`--wd` and `--output` are aliases, as are `--prev-result` and `--input`.** `bulkatac-motif-enrichment.py:420` registers `--output` as a synonym for `--wd` and `:413` registers `--input` as a synonym for `--prev-result` (both with explicit `dest=`) so the OmicsClaw runner's `--output <path>` + `--input <result.json>` injection works; if only `--output` is passed, sibling-detection finds `DA/result.json` next to it (`<output>/../DA/result.json`). Internal code references `args.wd` and `args.prev_result`.
- **`--prev-result` MUST point at a DA `result.json`, not a peak-calling one.** `bulkatac-motif-enrichment.py:509-513` hard-fails on `prev_skill != "bulkatac-DA"` (or a missing `da` key). This is a divergence from the chain-friendly behaviour of `bulkatac-footprinting`. If you only want enrichment on the full consensus set, you still need to have run `bulkatac-DA` first — the script will then silently skip `da_up`/`da_down` if those BEDs aren't present.
- **No `--demo` flag.** `bulkatac-motif-enrichment.py:479` jumps straight to HOMER + chain loading. Smoke-test via the full Step 1 → 2 → 3 → 4 chain with `--demo` flags where supported (only Step 1 has one), then this script with the same `--wd`.
- **`--mask` is a no-op; `--no-mask` is the real flag.** `bulkatac-motif-enrichment.py:439` defines `--mask` as `store_true` with `default=True`, so it's already on. The effective value at `:574` is `args.mask and not args.no_mask`; pass `--no-mask` to disable repeat masking for non-mammalian / non-vertebrate genomes where masking would discard too much sequence.
- **`--size` accepts an int (window in bp around peak center) or the literal `"given"` (use exact peak coordinates).** `bulkatac-motif-enrichment.py:569-572` tries `int()` first and falls back to the string. `--size 200` = HOMER default (±100 bp around peak center); `--size given` is recommended when peaks are already narrow / summit-centered.
- **HOMER genome install required unless `--genome-fasta` is passed.** `bulkatac-motif-enrichment.py:485-492` only checks the HOMER binary; the per-genome data is installed separately via `configureHomer.pl -install <genome>` and is NOT auto-installed. Bypass with `--genome-fasta /path/to/genome.fa` (HOMER's `-fasta` flag).
- **Background strategy differs per peak set.** `all_peaks` uses HOMER's default GC-matched genomic background (answers "what motifs are enriched in open chromatin?"). `da_up`/`da_down` use `-bg consensus_peaks.bed -chopify` (answers "what TFs drive condition-specific accessibility?"). Without the `-bg` swap, DA subsets just rediscover generic AP-1 / CTCF / etc. Documented in the script's docstring at `bulkatac-motif-enrichment.py:9-17`.
- **DA up / down peak sets silently skipped when absent.** `bulkatac-motif-enrichment.py:553-562` only logs to the logger; `result.json["motif_enrichment"]` will contain fewer entries than expected without surfacing an error. Inspect the length of that array to confirm which subsets actually ran.

## Key CLI

End-to-end after `bulkatac-DA` (auto-detects everything, runs `all_peaks` + `da_up` + `da_down`):

```bash
python skills/epigenomics/bulkatac/bulkatac-motif-enrichment/bulkatac-motif-enrichment.py \
    --wd ./atac_run --threads 32
```

Bypass HOMER's per-genome install via FASTA + use exact peak coordinates:

```bash
python skills/epigenomics/bulkatac/bulkatac-motif-enrichment/bulkatac-motif-enrichment.py \
    --wd ./atac_run \
    --genome hg38 --genome-fasta /refs/hg38/hg38.fa \
    --size given --threads 32
```

Non-mammalian (disable masking + tighter de novo lengths):

```bash
python skills/epigenomics/bulkatac/bulkatac-motif-enrichment/bulkatac-motif-enrichment.py \
    --prev-result /tmp/atac/DA/result.json \
    --wd /tmp/atac \
    --genome sacCer3 --genome-fasta /refs/sacCer3.fa \
    --no-mask --denovo-length 6,8,10 --n-motifs 15
```

## See also

- `references/parameters.md` — every CLI flag with type + default (auto-generated from `parameters.yaml`).
- `references/methodology.md` — HOMER `findMotifsGenome.pl` invocation per peak set, GC-matched genomic vs `-bg -chopify` consensus background, hypergeometric ZOOPS scoring, de novo motif discovery procedure, autonormalization.
- `references/output_contract.md` — full output tree, HOMER native output schemas (`knownResults.txt`, `homerResults.html`, `homerMotifs.all.motifs`), `top_motif_summary.tsv` schema, `result.json["motif_enrichment"]` keys.
- Adjacent skills:
  - Upstream — `bulkatac-DA` (REQUIRED; produces the DA result.json that this script chains off).
  - Parallel — `bulkatac-footprinting` (TOBIAS — different question: which motifs are actively *bound* in vivo, not just enriched). Pair them for full TF-level interpretation: enrichment surfaces candidates, footprinting confirms occupancy.
  - Downstream — none yet (manual integration with TF expression / GRN analysis lives outside the skill set).
