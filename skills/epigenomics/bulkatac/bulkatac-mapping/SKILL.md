---
name: bulkatac-mapping
description: Load when aligning bulk ATAC-seq trimmed FASTQs to a reference and computing ENCODE post-alignment QC (NRF/PBC1/PBC2, %mito, TSS enrichment, fragment-length, BigWig). Skip when reads aren't yet trimmed (start at bulkatac-preprocessing), for single-cell ATAC (use scatac-preprocessing), or for ChIP-seq alignment.
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- atac-seq
- alignment
- mapping
- qc
- bowtie2
- bwa
- samtools
- deeptools
- encode-qc
requires:
- pandas
- numpy
---

## When to use

The user has trimmed FASTQs from `bulkatac-preprocessing` and wants ENCODE-style alignment to a reference genome (Bowtie2 by default; BWA MEM optional), MAPQ-filtered + deduplicated BAMs, library-complexity metrics (NRF/PBC1/PBC2), TSS enrichment, fragment-length distribution, and RPGC-normalised BigWig tracks. The reference is auto-downloaded and indexed if no pre-built index is supplied. Skip for scATAC (`scatac-preprocessing`), ChIP-seq, or to start from raw FASTQs — go to `bulkatac-preprocessing` first.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Step-1 result | `<project>/preprocessing/result.json` from `bulkatac-preprocessing` | Yes (via `--prev-result`, or sibling-detected from `--wd`) |
| Reference genome | Build name (`hg38`, `mm10`, `sacCer3`, …) via `--genome` | Required only if the upstream `result.json` has no genome |
| Aligner index | Pre-built Bowtie2 or BWA index | Optional — auto-downloaded + built into `--ref-dir` if absent |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Mapping + QC tables, ENCODE thresholds, usable-read rule |
| Result envelope | `<output>/result.json` | Carries `mapping`, `qc_after_mapping`, `encode_qc_thresholds`, `genome_files`, chained from Step 1 |
| Per-sample summary | `<output>/mapping_summary.csv` | One row per sample — align rate, fragments, %mito, NRF/PBC, dedup, downsample target |
| Sample BAMs | `<output>/bam/<sample>.dedup.bam` (or `.no_blacklist.bam` if blacklist applied) + `.bai` | Filtered + deduplicated (MAPQ ≥ 30, no chrM, no dups); `<sample>.ds.bam` when `--downsample` |
| RPGC signal | `<output>/bigwig/<sample>.rpgc.bw` | deepTools `bamCoverage` (binSize 10, `--ignoreDuplicates`, `--minMappingQuality 30`) |
| Post-align QC | `<output>/qc_after_mapping/qc_after_mapping_summary.csv` + `tss_enrichment/` + `fragment_length/` | Per-sample TSS profiles, fragment-length histograms, and combined-cohort PNGs |
| Reproducibility | `<output>/reproducibility/{commands.sh,environment.txt}` | Re-run command + pinned Python versions |

## Flow

1. Locate the upstream Step-1 `result.json`: use `--prev-result` if passed, otherwise the sibling `<project>/preprocessing/result.json` (`--wd`'s parent); hard-fail if neither resolves (`bulkatac-mapping.py:506-517`).
2. Reconstruct the `SampleSheet` and trimmed-FASTQ paths from Step 1, then resolve `--genome` (CLI overrides the upstream value) (`bulkatac-mapping.py:523-532`).
3. Use `--output` directly as the output dir, and `<project>/reference_<genome>/` (a sibling) as the default reference dir (`bulkatac-mapping.py:535-540`).
4. Resolve the aligner index: honour `--bwa-index` / `--bowtie2-index` if supplied, otherwise call `prepare_reference` to download FASTA + blacklist and build the index (`bulkatac-mapping.py:546-583`).
5. Step 2a — `run_all_mapping`: Bowtie2 / BWA → ENCODE filter (`-F 1804 -f 2 -q 30` PE / `-F 1796 -q 30` SE) → chrM removal → `samtools markdup -r` → optional blacklist subtract → NRF / PBC1 / PBC2 → optional cross-sample downsample (`bulkatac-mapping.py:601-613`).
6. Step 2b — `run_all_qc_after_mapping`: BigWig (RPGC), TSS enrichment via deepTools `computeMatrix`, fragment-length distribution per sample + cohort (`bulkatac-mapping.py:619-625`).
7. Write `report.md`, `result.json`, `reproducibility/`, `README.md`, then print a stdout summary (`bulkatac-mapping.py:634-662`).

## Gotchas

- **No `--demo` flag.** Unlike `bulkatac-preprocessing`, this script has no synthetic-data path — `bulkatac-mapping.py:502` jumps straight to argparse + prev-result loading. To smoke-test, run `bulkatac-preprocessing --demo` first; the resulting `result.json` becomes valid input here.
- **Chains via `--prev-result` (also accepts `--input` as an alias).** `bulkatac-mapping.py:421-424` reads the upstream skill's `result.json` to reconstruct the sample sheet + trimmed FASTQs. `--wd` is aliased to `--output` (`bulkatac-mapping.py:426-427`) so the OmicsClaw runner's `--output <path>` + `--input <result.json>` injection works; if only `--output` is passed, sibling-detection finds `preprocessing/result.json` next to it (`<output>/../preprocessing/result.json`).
- **BAMs are NOT Tn5-shifted (+4/-5).** Per the design note at `bulkatac-mapping.py:23-25`, the +4/-5 offset is left to downstream tools (TOBIAS `ATACorrect` applies it and corrects Tn5 sequence bias; MACS2 has `--shift`/`--extsize`). Pre-shifting here would double-correct.
- **`--downsample` is OFF by default.** ENCODE relies on RPGC for visualisation and DESeq2/edgeR size factors for DA; `bulkatac-mapping.py:464-472` documents the trade-off and cites Reske et al. 2020 (PMID:32321567) which recommends subsampling to equivalent complexity for DA fairness. Pass `--downsample` if any sample is significantly shallower than the others.
- **MAPQ ≥ 30 is hard-coded in the ENCODE filter.** Not exposed as a CLI flag; see the filter spec at `bulkatac-mapping.py:47-48`. Reads with MAPQ 1–29 (e.g. mappers like Bowtie2 reporting alignment ambiguity) are dropped, which can substantially reduce usable depth on repeat-rich genomes.
- **`--bwa-index` and `--bowtie2-index` are mutually exclusive.** `bulkatac-mapping.py:443-447` enforces this via argparse. The aligner choice (`--aligner`) must match the index format you pass — `--aligner bwa --bowtie2-index ...` is silently incoherent and will fail at run time.
- **Reference auto-download writes ~3-5 GB.** When no `--*-index` is given, `bulkatac-mapping.py:566-573` calls `prepare_reference` which `wget`s the FASTA, builds the aligner index, and downloads the ENCODE blacklist BED into `--ref-dir` (default `<project>/reference_<genome>/`, a sibling of the mapping output dir). First run on hg38 / mm10 takes 30-60 min wall clock and noticeable disk; subsequent runs reuse the index.

## Key CLI

End-to-end run after `bulkatac-preprocessing` (auto-detects prev-result, auto-downloads hg38 reference):

```bash
python skills/epigenomics/bulkatac/bulkatac-mapping/bulkatac-mapping.py \
    --wd ./atac_run --genome hg38 --threads 32
```

Use an existing Bowtie2 index (skips download), classify TSS tier as cell-line:

```bash
python skills/epigenomics/bulkatac/bulkatac-mapping/bulkatac-mapping.py \
    --wd ./atac_run --genome hg38 \
    --bowtie2-index /refs/hg38/bowtie2/hg38 \
    --blacklist /refs/hg38/ENCFF356LFX.bed.gz \
    --cell-type cell_line --threads 32
```

BWA MEM + cross-sample downsampling (Reske et al. DA-fairness setting):

```bash
python skills/epigenomics/bulkatac/bulkatac-mapping/bulkatac-mapping.py \
    --prev-result /tmp/atac/preprocessing/result.json \
    --wd /tmp/atac --genome hg38 \
    --aligner bwa --bwa-index /refs/hg38/bwa/hg38.fa \
    --downsample --keep-intermediates --threads 48
```

## See also

- `references/parameters.md` — every CLI flag with type + default (auto-generated from `parameters.yaml`).
- `references/methodology.md` — Bowtie2 / BWA flag derivation, ENCODE filter rationale, NRF/PBC1/PBC2 formulas, TSS enrichment + fragment-length QC pipelines, downsampling debate.
- `references/output_contract.md` — full output tree, `mapping_summary.csv` + `qc_after_mapping_summary.csv` column schemas, `result.json` keys.
- Adjacent skills:
  - Upstream — `bulkatac-preprocessing` (must run first to produce `preprocessing/result.json`).
  - Downstream — `bulkatac-peak-calling` (MACS2 + consensus peaks consumes these deduplicated BAMs).
  - Parallel — `scatac-preprocessing` (single-cell ATAC; uses different alignment + QC tooling).
