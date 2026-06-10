# Methodology — bulkchip-peak-annotation

> Implemented. Annotation only; GO/KEGG functional enrichment is a separate skill.

## Capabilities

- Genomic annotation: assign each ChIP-seq peak to a genomic feature and its
  nearest gene, with the distance to the nearest TSS.
- Feature-distribution donut + TSS-distance profile.
- Target-gene extraction: the unique nearest genes whose TSS lies within a
  configurable window of a peak — the gene set handed downstream to GO/KEGG
  enrichment.

This is the annotation half of the ChIP-relevant downstream that replaces
ATAC's TOBIAS footprinting.

## Workflow

1. **Resolve inputs**
   - Peak subset: `consensus` (`consensus.consensus_bed`) or `condition`
     (first `peak_calling[].peaks_file`) from Step 3, or DA `up`/`down`
     (`differential_binding.up_bed` / `down_bed`) via `--de-result` or by
     chaining from a `bulkchip-DA` result.json. A DA result is detected by
     `skill == "bulkchip-DA"` or the presence of a `differential_binding` block;
     its `prev_result` is followed back to peak-calling for genome/GTF.
   - Annotation source: GTF (`--gtf` > auto-detected `genome_files.gtf`), else
     the genome NAME (`--genome` > `sample_sheet.genome`) used as the HOMER
     genome.

2. **Annotation** (`annotate_peaks`) — priority ladder:
   1. **HOMER + GTF** — `annotatePeaks.pl <peaks> none -gtf genes.gtf`
      (no genome install needed). Rich feature categories (Promoter-TSS, TTS,
      5'UTR, 3'UTR, Exon, Intron, Intergenic, Non-coding) + nearest gene +
      distance to TSS.
   2. **HOMER + genome** — `annotatePeaks.pl <peaks> <genome>` (requires
      `configureHomer.pl -install <genome>`). Falls back if the genome is not
      installed.
   3. **bedtools + GTF** — `bedtools closest` against 1 bp TSS positions
      extracted from the GTF; distance-based categories (Promoter < 1 kb /
      Proximal 1–5 kb / Distal 5–50 kb / Intergenic > 50 kb).
   4. **Neither available** — write a well-formed feature-less
      `annotated_peaks.tsv` (peaks pass through; gene/category blank), warn,
      and do not crash.

3. **Plots** — feature-distribution donut (`peak_annotation_pie`) and
   log10 distance-to-TSS histogram (`peak_tss_distance`). Both skip silently
   when there is nothing to plot.

4. **Target genes** — unique nearest genes with `|distance to TSS| ≤
   --tss-window`, in first-seen order. Written to `result.json` as
   `annotation.target_genes` for the downstream enrichment skill.

## Method notes

- **TSS window by mark type**: promoter marks / TFs (H3K4me3, CTCF) → tight
  window (~3 kb); enhancer marks (H3K27ac, H3K4me1) → wide window (~10 kb)
  since they act distally.
- **Annotation vs motif**: annotation answers "what genes/pathways", motif
  (`bulkchip-motif-enrichment`) answers "what sequence" — complementary.
- **HOMER does not read gzipped GTF**: gzipped GTFs are transparently
  decompressed next to the original before being passed to `annotatePeaks.pl`.

## Output contract

`result.json`:

```json
{
  "skill": "bulkchip-peak-annotation",
  "version": "0.1.0",
  "log": "<wd>/bulkchip-peak-annotation.log",
  "params": { "...": "..." },
  "annotation": {
    "peak_subset": "consensus",
    "annotated_tsv": "<path>",
    "feature_counts": { "Promoter-TSS": 1234, "Intron": 567, "...": 0 },
    "n_target_genes": 4321,
    "target_genes": ["GENE1", "GENE2", "..."],
    "pie_png": "<path>",
    "tss_dist_png": "<path>",
    "genome": "hg38",
    "tss_window": 3000
  },
  "prev_result": "<upstream result.json path>"
}
```

`annotation/annotated_peaks.tsv` columns: `peak_chr, peak_start, peak_end,
nearest_gene, distance, category` (HOMER adds `detailed_annotation, gene_type`).

## Dependencies

- Python: pandas, numpy, matplotlib (all lazy-imported)
- External: HOMER (`annotatePeaks.pl`) or bedtools + a GTF
  (see `0_setup_env_for_bulkchip.sh`)

## References

- HOMER annotatePeaks.pl — http://homer.ucsd.edu/homer/ngs/annotation.html
- ChIPseeker (Yu et al. 2015) — https://doi.org/10.1093/bioinformatics/btv145
