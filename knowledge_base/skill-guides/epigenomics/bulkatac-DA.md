---
doc_id: skill-guide-bulkatac-DA
title: OmicsClaw Skill Guide — Bulk ATAC Differential Accessibility
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkatac-DA, bulkatac-da, bulkatac-differential-accessibility]
search_terms: [bulk ATAC differential accessibility, pyDESeq2, ATAC volcano, padj, BH-FDR, consensus peaks, IGV BED tracks]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ATAC Differential Accessibility

**Status**: implementation-aligned guide derived from the current OmicsClaw
`bulkatac-DA` skill. This guide explains the real wrapper behavior, public
parameter semantics, and method-selection logic. It does not imply that
multi-factor, time-course, or shrinkage-aware accessibility workflows are
already exposed.

## Purpose

Use this guide when you need to decide:

- whether the input is suitable for differential accessibility (DA) right now
- how to explain the current pyDESeq2 two-group contrast without overclaiming
  scope
- how to tune contrast selection and the `padj` / `log2FC` significance cuts
- how to read the volcano plot and the IGV-ready BED tracks correctly

## Step 1: Inspect The Data First

Before running DA, check:

- **Upstream state**:
  - the wrapper chains off `bulkatac-peak-calling`'s `result.json` — it does
    not start from BAMs or FASTQs
  - pass `--prev-result` explicitly, or let `--wd` sibling-detect
    `<project>/peak_calling/result.json`
- **Count matrix**:
  - the wrapper consumes raw integer `featureCounts` output from the consensus
    peak set — no manual normalization; DESeq2 size factors are internal
  - paired-end counts are fragment-level (Step 3 sets `--countReadPairs`),
    which is what the negative-binomial GLM expects
- **Conditions**:
  - the sample sheet must label at least two distinct conditions; a one-label
    pilot sheet hard-fails — DA is not applicable, add a comparator first
- **Annotation**:
  - the Step-3 `annotated_peaks.tsv` is joined when present so each DA peak
    gets a nearest-gene / feature-category label; absence is a silent warning
- **Workflow scope**:
  - the current wrapper runs exactly one two-group contrast; multi-factor,
    paired, or time-course designs are not exposed

Important implementation notes in current OmicsClaw:

- The DA engine is pyDESeq2 (negative-binomial GLM + Wald test).
- `log2FoldChange` is **unshrunk** — fine for threshold testing, not for
  ranking; for apeglm / ashr shrinkage, re-run pyDESeq2 directly.
- Significance is called on the **BH-adjusted p-value `padj`**, never raw
  `pvalue`.
- Re-running with different thresholds writes parallel trees, not overwrites.

## Step 2: Choose The Contrast Deliberately

### Explicit `--treat` / `--control`

Best when:

- the sample sheet has three or more conditions
- you know which pair is biologically meaningful
- you want the contrast naming (`<treat>_vs_<control>`) to be predictable

Wrapper behavior:

- the contrast numerator is `treat`, denominator is `control`
- `log2FoldChange > 0` means "more accessible in `treat`"

### Auto-contrast (both flags omitted)

Best when:

- the sample sheet has exactly two conditions and the pairing is unambiguous

Wrapper behavior:

- unique condition labels are sorted alphabetically
- `control = sorted[0]`, `treat = sorted[1]`
- with three or more conditions only this single first pair is tested

Important warning:

- auto-contrast is alphabetical, not biological — for any non-trivial design
  pass `--treat` / `--control` explicitly so the right pair runs

## Step 3: Tune The Significance Cuts In A Stable Order

### Significance thresholds

Tune in this order:

1. `--padj`
2. `--lfc`

Guidance:

- `--padj` is the BH-adjusted p-value cut; lower it (e.g. `0.01`) to be
  stricter when there are many called peaks
- `--lfc` is the absolute `log2FoldChange` cut; raise it (e.g. `1.5`) to focus
  on larger-effect accessibility changes
- direction labels are assigned as: `up` if `padj < --padj` AND
  `log2FoldChange ≥ --lfc`; `down` if `padj < --padj` AND
  `log2FoldChange ≤ -lfc`; `ns` otherwise
- peaks with `NA` padj (removed by DESeq2 independent filtering) are labelled
  `ns` and counted in `n_ns`

Important warning:

- the significance call uses `padj`, NOT raw `pvalue` — across thousands of
  peaks raw p is not multiple-testing-corrected and would inflate false
  positives; this is the documented, correct behavior

### Annotation join

Guidance:

- leave annotation on by default to get nearest-gene context per peak
- pass `--skip-annotation` for faster re-runs or when no GTF / HOMER
  annotation is available

Important warning:

- a missing annotation TSV is a silent warning, not an error — confirm via
  `result.json["da"]["annotation_source"]`

## Step 4: Show An Effective Run Summary Before Execution

Before execution, summarize the real run in a compact block, for example:

```text
About to run bulk ATAC differential accessibility
  Engine: pyDESeq2 (negative-binomial GLM + Wald test)
  Contrast: T15_vs_T0 (treat over control)
  Significance: padj < 0.05 (BH-FDR), |log2FC| >= 1.0
  Annotation join: on (Step-3 annotated_peaks.tsv)
  Note: results nest under <output>/DA/<contrast>/<param_tag>/.
```

## Step 5: What To Say After The Run

- If `n_up` / `n_down` are near zero: revisit `--padj` first, then `--lfc`.
- If too many peaks pass: tighten `--padj` to `0.01` and/or raise `--lfc`.
- If the wrong pair was tested: pass `--treat` / `--control` explicitly and
  re-run (it writes a parallel tree).
- If results lack gene names: check `annotation_source` — the join was
  skipped or the file was absent.
- If the contrast hard-failed on entry: the sample sheet has fewer than two
  conditions; DA is not applicable.

## Step 6: Explain Outputs Correctly

When summarizing results:

- describe `DA/<contrast>/<param_tag>/da_results_<contrast>.tsv` as the
  per-peak pyDESeq2 table — `baseMean`, `log2FoldChange`, `lfcSE`, `stat`,
  `pvalue`, `padj`, `direction`, plus annotation columns when joined
- describe `da_summary_<contrast>.csv` as the one-row contrast summary
  (`n_tested`, `n_up`, `n_down`, `n_ns`, thresholds)
- describe `da_peaks_up_<contrast>.bed` (red `255,0,0`),
  `da_peaks_down_<contrast>.bed` (blue `0,0,255`), and
  `da_peaks_all_<contrast>.bed` (direction-coloured) as BED9 tracks with a
  `track ... itemRgb="On"` header for direct IGV / WashU / UCSC loading
- describe `plots/<contrast>/<param_tag>/volcano_<contrast>.{pdf,png}` as the
  volcano figure — the y-axis is `-log10(padj)` and up / down / ns colouring
  uses `padj` plus the `--lfc` cut, the **same statistic** as the summary and
  BED tracks, so the legend always matches the text
- describe `volcano_<contrast>.tsv` as the underlying point data (carries
  both `pvalue` and `padj`) for custom re-plotting
- describe `result.json["da"]` as the structured contrast envelope with
  counts, thresholds, and artifact paths

Do **not** say "differential accessibility completed" for a multi-factor or
time-course design — the wrapper only runs a single two-group contrast.
Do **not** describe the volcano as raw-p-value based; significance is `padj`.

OmicsClaw is a research and educational tool for multi-omics analysis. It is
not a medical device and does not provide clinical diagnoses. Consult a
domain expert before making decisions based on these results.
