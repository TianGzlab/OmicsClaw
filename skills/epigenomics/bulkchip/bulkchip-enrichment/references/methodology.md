# Methodology — bulkchip-enrichment

> Implemented (gseapy-backed). See `_lib/enrichment.py`.

## Capability

GO / KEGG functional **over-representation analysis (ORA)** on the ChIP
target-gene set. Given the genes assigned to bound peaks, ORA asks which
gene-set libraries (GO terms, KEGG pathways) are statistically enriched among
those targets relative to the genomic background.

This skill is the gene/pathway-level complement to the sequence-level
`bulkchip-motif-enrichment`, and consumes the gene list produced by the
separate `bulkchip-peak-annotation` skill — it never annotates peaks itself.

## Workflow

1. **Resolve target genes** — read the `bulkchip-peak-annotation` `result.json`:
   - primary: `annotation.target_genes` (genes whose TSS lies within the
     annotation skill's TSS window of a peak);
   - fallback: parse the nearest-gene column from `annotation.annotated_tsv`;
   - hard-fail with guidance only if neither is available.
2. **Over-representation** (`run_functional_enrichment`)
   - for each `--gene-sets` library run
     `gseapy.enrichr(gene_list=target_genes, gene_sets=<name or .gmt>,
     organism=<--organism>)`;
   - normalize results to a stable CSV contract:
     `term, overlap, adjusted_p_value, p_value, combined_score, genes`;
   - count significant terms at `--padj` and render a top-terms dotplot
     (-log10 adjusted p-value vs gene count).

## Method notes

- **ORA vs GSEA**: ChIP target genes are an unranked set (a gene is bound or
  not), so over-representation (hypergeometric / Fisher via Enrichr) is the
  natural test — no ranking metric is required.
- **Organism**: auto-derived from the upstream genome build (`sacCer3→yeast`,
  `hg38→human`, `mm10→mouse`, `dm6→fly`, `ce11→worm`, `danRer11→fish`) so it
  always matches the gene symbols. `--genome` overrides the build; `--organism`
  overrides the derived Enrichr organism for builds outside the map (unmapped →
  `human` + warning).
- **Multiple-testing**: Enrichr reports Benjamini-Hochberg adjusted p-values;
  significance is taken at `--padj` (default 0.05).
- **Offline enrichment**: supply a local `.gmt` via `--gmt` when Enrichr's
  online API is unavailable; it is used for every requested library.
- **Graceful degradation**: a missing `gseapy`, a failed Enrichr call, or an
  empty target-gene set logs a warning and writes a header-only CSV with
  `n_terms=0` — the skill never crashes the pipeline.

## Demo

For the SPT5 yeast demo, nothing extra is needed — the organism is derived from
the upstream `sacCer3` genome (→ yeast); the target genes come from the upstream
`bulkchip-peak-annotation` run on the SPT5 peaks.

## Dependencies

- Python: pandas, numpy, gseapy, matplotlib
- Network (optional): Enrichr API for online gene-set libraries; offline `.gmt`
  files are supported via `--gmt`.

## References

- gseapy / Enrichr — https://github.com/zqfang/GSEApy
- Chen et al. 2013 (Enrichr) — https://doi.org/10.1186/1471-2105-14-128
- Kuleshov et al. 2016 (Enrichr) — https://doi.org/10.1093/nar/gkw377
