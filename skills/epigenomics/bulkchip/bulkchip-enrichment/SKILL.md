---
name: bulkchip-enrichment
description: "Load when running GO/KEGG functional over-representation (gseapy.enrichr) on the target-gene set from bulkchip-peak-annotation. Consumes the gene list only. Skip when you need to annotate peaks (use bulkchip-peak-annotation) or do motif analysis (use bulkchip-motif-enrichment). Degrades gracefully when gseapy/Enrichr is offline."
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- chip-seq
- functional-enrichment
- go
- kegg
- gseapy
- enrichr
- ora
requires:
- pandas
- numpy
- gseapy
- matplotlib
---

> **Status: implemented** (gseapy-backed). See `_lib/enrichment.py`.

## When to use

The user has a ChIP-seq target-gene set from `bulkchip-peak-annotation` (genes
assigned to bound peaks) and wants to know which biological processes / pathways
those bound regions regulate, via GO/KEGG over-representation (ORA). This is a
gene-set-level question. Skip for peak→gene annotation itself (that is
`bulkchip-peak-annotation`, run first) and for sequence motif discovery
(`bulkchip-motif-enrichment`).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Annotation result | `bulkchip-peak-annotation` `result.json` with `annotation.target_genes` (or `annotation.annotated_tsv` for fallback) | Yes (via `--prev-result`, or sibling-detected from `--wd`) |
| Offline GMT | `.gmt` gene-set library | Optional (`--gmt`, for air-gapped environments) |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Significant terms per library + disclaimer |
| Result envelope | `<output>/result.json` | `enrichment` block (per-library CSV/dotplot/n_terms) |
| Enrichment | `<output>/enrichment/` | per-library results CSV (`term, overlap, adjusted_p_value, genes`) + dotplot PNG |
| Summary | `<output>/enrichment_summary.csv` | one row per gene-set library |

## Flow

1. Locate the upstream `bulkchip-peak-annotation` `result.json`; extract
   `annotation.target_genes` (fallback: parse the nearest-gene column of
   `annotation.annotated_tsv`).
2. For each `--gene-sets` library, run `gseapy.enrichr(gene_list=target_genes,
   gene_sets=<name or .gmt>, organism=<--organism>)`.
3. Write one results CSV + dotplot PNG per library, an `enrichment_summary.csv`,
   then `report.md`, `result.json`, `reproducibility/`, `README.md`.

## Gotchas

- **Consumes a gene list, does not annotate.** Peak→gene assignment is the
  separate `bulkchip-peak-annotation` skill; run it first so `target_genes` exists.
- **Graceful degradation, never a crash.** A missing `gseapy`, an Enrichr
  network failure, or an empty target-gene set produces empty (header-only)
  results with `n_terms=0` and a warning — not an error.
- **Organism is auto-derived from the genome.** The Enrichr organism is mapped
  from the upstream genome build (`sacCer3→yeast`, `hg38→human`, `mm10→mouse`,
  `dm6→fly`, `ce11→worm`, `danRer11→fish`); you normally pass nothing. Use
  `--genome` to override the build, or `--organism` only for a build outside the
  map (e.g. rat → falls back to `human` with a warning unless overridden).
- **Offline enrichment** — Enrichr libraries are fetched online by default; pass
  an offline `--gmt` library in air-gapped environments.
- **Empty/intergenic target set → sparse enrichment** — a mostly-intergenic peak
  set yields few target genes and few enriched terms.

## Key CLI

```bash
# Organism is derived from the upstream genome — nothing extra needed:
python skills/epigenomics/bulkchip/bulkchip-enrichment/bulkchip-enrichment.py \
    --prev-result ./chip_run/annotation/result.json \
    --wd ./chip_run/enrichment --gene-sets GO_Biological_Process,KEGG
```

For the SPT5 yeast demo this just works (`sacCer3 → yeast`); add `--organism <x>`
only to override an unmapped genome.

## See also

- `references/methodology.md` — ORA method, gseapy.enrichr usage, offline GMT, graceful fallback.
- Adjacent skills:
  - Upstream — `bulkchip-peak-annotation` (produces `target_genes`).
  - Sibling — `bulkchip-motif-enrichment` (HOMER motif enrichment, sequence-level).
  - Parallel — `bulkatac-motif-enrichment` (the ATAC counterpart).
