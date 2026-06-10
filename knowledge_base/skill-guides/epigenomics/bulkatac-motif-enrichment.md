---
doc_id: skill-guide-bulkatac-motif-enrichment
title: OmicsClaw Skill Guide — Bulk ATAC Motif Enrichment
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkatac-motif-enrichment]
search_terms: [bulk ATAC motif enrichment, HOMER findMotifsGenome, de novo motif discovery, transcription factor, GC-matched background, consensus background]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ATAC Motif Enrichment

**Status**: implementation-aligned guide derived from the current OmicsClaw
`bulkatac-motif-enrichment` skill. This guide explains the real wrapper
behavior, public parameter semantics, and method-selection logic. It does not
imply that ChIP-seq motif workflows or TF-expression integration are already
exposed.

## Purpose

Use this guide when you need to decide:

- whether the input is suitable for HOMER motif enrichment right now
- how to explain the per-peak-set background strategy without overclaiming
- how to tune the HOMER window, repeat masking, and de novo search settings
- how to read known-motif vs de novo motif output correctly

## Step 1: Inspect The Data First

Before running motif enrichment, check:

- **Upstream state**:
  - the wrapper chains off a `bulkatac-DA` `result.json` — it hard-fails if
    `prev_skill != "bulkatac-DA"` or no `da` key exists
  - it then walks the DA `prev_result` back to peak-calling for the consensus
    BED
  - even if you only want enrichment on the full consensus set, `bulkatac-DA`
    must have run first
- **Peak sets**:
  - three peak sets are processed — `all_peaks` (full consensus), `da_up`, and
    `da_down`
  - the DA up / down BEDs are picked up from the Step-4 envelope; either or
    both are silently skipped if absent (inspect the `motif_enrichment` array
    length to confirm what ran)
- **Genome data**:
  - HOMER needs per-genome data installed via `configureHomer.pl -install`,
    OR a FASTA passed via `--genome-fasta` (HOMER's `-fasta` bypass)
  - only the HOMER binary is hard-checked; per-genome data is not auto-installed
- **Workflow scope**:
  - this is over-representation analysis — it surfaces which motifs accumulate
    in a peak set, not which TFs are actively bound (that is footprinting)

Important implementation notes in current OmicsClaw:

- The engine is HOMER `findMotifsGenome.pl` (Heinz et al. 2010).
- Each peak set gets both known-motif enrichment and de novo discovery.
- `--mask` is a no-op default-on flag; `--no-mask` is the real toggle.
- An empty peak set writes a `NOTE_no_peaks.txt` sentinel rather than failing.

## Step 2: Understand The Background Strategy

The background differs per peak set — this is the core method choice and it
is fixed by the wrapper, not user-tunable.

### `all_peaks` — GC-matched genomic background

- foreground: the full consensus peak set (union across conditions)
- background: HOMER's default GC-matched random genomic regions
- question answered: "what motifs is the open-chromatin landscape enriched
  for vs the genome at large?"

### `da_up` / `da_down` — consensus background (`-bg ... -chopify`)

- foreground: the DA-up or DA-down subset BED
- background: the consensus peak set, passed as `-bg consensus_peaks.bed`
  with `-chopify` (chops background regions to the foreground peak size)
- question answered: "what motifs drive *condition-specific* accessibility
  changes?"

Important warning:

- without the consensus-background swap, the DA subsets would just rediscover
  generic open-chromatin motifs (AP-1, CTCF) — the swap is what surfaces
  condition-specific TFs

## Step 3: Tune HOMER Parameters In A Stable Order

### Window and masking

Tune in this order:

1. `--size`
2. `--no-mask`

Guidance:

- `--size 200` (HOMER default) scans ±100 bp around the peak center
- `--size given` uses the peak's exact coordinates — recommended when peaks
  are already narrow and summit-centered (as MACS2 peaks are)
- repeat masking is on by default; pass `--no-mask` for non-mammalian /
  non-vertebrate genomes (yeast, plants) where masking discards too much
  sequence

Important warning:

- `--mask` does nothing (it is `store_true` with `default=True`) — the
  effective value is `args.mask and not args.no_mask`, so only `--no-mask`
  changes behavior

### De novo search

Tune in this order:

1. `--denovo-length`
2. `--n-motifs`

Guidance:

- `--denovo-length` (default `8,10,12`) sets the de novo motif lengths
  searched; use shorter lengths (e.g. `6,8,10`) for compact non-vertebrate
  motifs
- `--n-motifs` caps the number of de novo motifs reported
- `--threads` parallelises HOMER's de novo search and is the main cost driver

### Genome resolution

Guidance:

- `--genome` overrides the Step-3 auto-detected genome short-name
- `--genome-fasta` bypasses the HOMER per-genome install entirely — slightly
  slower per run but removes the install dependency

## Step 4: Show An Effective Run Summary Before Execution

Before execution, summarize the real run in a compact block, for example:

```text
About to run bulk ATAC motif enrichment
  Engine: HOMER findMotifsGenome.pl
  Peak sets: all_peaks (genomic bg), da_up + da_down (consensus bg -chopify)
  Window: --size given   Masking: off (--no-mask, non-mammalian genome)
  De novo: lengths 8,10,12, top 25 motifs, 32 threads
  Note: each peak set gets known-motif enrichment + de novo discovery.
```

## Step 5: What To Say After The Run

- If `da_up` / `da_down` are missing from the output: the DA BEDs were absent
  upstream — inspect the `motif_enrichment` array length.
- If a peak set has a `NOTE_no_peaks.txt`: that subset was empty at the DA
  thresholds — not a HOMER failure; loosen `bulkatac-DA`'s `--padj` / `--lfc`.
- If HOMER hard-failed at startup: `findMotifsGenome.pl` is not on `PATH`.
- If the genome short-name is unrecognised: pass `--genome-fasta` to bypass
  the HOMER per-genome install.
- If only generic motifs (AP-1, CTCF) appear in `da_up` / `da_down`: that is
  expected if accessibility changes are not strongly TF-driven — the
  consensus background already removes generic open-chromatin signal.

## Step 6: Explain Outputs Correctly

When summarizing results:

- describe `{all_peaks,da_up,da_down}/knownResults.txt` as the HOMER-native
  known-motif table — hypergeometric `P-value`, `Log P-value`,
  `q-value (Benjamini)`, and `% Target` / `% Background` enrichment
- describe `knownResults.html` and `homerResults.html` as the interactive
  HOMER reports (motif logos + p-values) — open in a browser, no server needed
- describe `homerMotifs.all.motifs` as all de novo PWMs in HOMER `.motifs`
  format, re-usable via `-mknown` to scan other peak sets
- describe `knownResults/` and `homerResults/` as per-motif logo / detail
  assets emitted by HOMER itself
- describe `top_motif_summary.tsv` as the cross-peak-set ranked motif table —
  the single file to read for "what TFs matter in this experiment?"
- describe `plots/top_known_motifs_<set>.{pdf,png}` and
  `top_denovo_motifs_<set>.{pdf,png}` as the top-motif bar charts ranked by
  `-log10(p-value)`
- note that HOMER reports BH q-values for known motifs but de novo p-values
  are empirical against the foreground k-mer null and are not corrected

Do **not** say a TF is "bound" or "active" — enrichment surfaces candidates;
binding occupancy is `bulkatac-footprinting`'s question. Pair the two skills
for full TF-level interpretation.

OmicsClaw is a research and educational tool for multi-omics analysis. It is
not a medical device and does not provide clinical diagnoses. Consult a
domain expert before making decisions based on these results.
