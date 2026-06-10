# Methodology — bulkchip-DA

> Implemented (pyDESeq2-backed). See `_lib/DA.py`.

## Capabilities

- Two-condition differential binding on the consensus peak count matrix via
  pyDESeq2; volcano plot; up/down peak BED tracks.

Does not call peaks, annotate, or find motifs (sibling skills).

## Workflow

1. **Load counts** — `consensus.count_matrix` (raw featureCounts, peaks ×
   samples) from Step 3.
2. **Design** — condition factor from the sample sheet; resolve `--treat`
   (numerator) and `--control` (denominator); default to the two conditions in
   alphabetical order with a warning.
3. **pyDESeq2** (`run_differential_binding`)
   - `DeseqDataSet` with `design="~condition"`; size-factor normalization;
     dispersion estimation; Wald test.
   - LFC shrinkage (`apeglm` / `ashr`) for ranking.
4. **Threshold + outputs** — call up/down at `padj < --padj` and
   `|log2FC| > --lfc`; write `differential_binding.csv`, `volcano.png`,
   `up_peaks.bed`, `down_peaks.bed`.

## Method notes

- **Raw counts only** — pyDESeq2 estimates its own size factors; pre-normalised
  input biases dispersion.
- **Binding, not expression** — fold-changes reflect ChIP occupancy / mark
  deposition at peaks. Feed up/down BEDs into `bulkchip-motif-enrichment` or
  `bulkchip-annotation-enrichment` to interpret biologically.
- Mirrors `bulkatac-DA` exactly (same matrix schema) — accessibility there,
  binding here.

## Demo

No implemented demo dataset yet (scaffold).

## Dependencies

- Python: pandas, numpy, pydeseq2, matplotlib (see `0_setup_env_for_bulkchip.sh`)

## References

- pyDESeq2 — https://github.com/owkin/PyDESeq2
- DESeq2 (Love et al. 2014) — https://doi.org/10.1186/s13059-014-0550-8
- DiffBind (concept reference) — https://doi.org/10.1038/nature10730
