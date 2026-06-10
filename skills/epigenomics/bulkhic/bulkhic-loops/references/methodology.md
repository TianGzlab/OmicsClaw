# Methodology — bulkhic-loops

> Implemented (cooltools). See `_lib/loops.py`.

## Capability

Chromatin loop (dot) calling from a balanced `.mcool`.

## Workflow

1. **expected-cis** — `cooltools expected-cis` → observed/expected normalisation
   (required by dots).
2. **dots** — `cooltools dots --fdr 0.02 --max-loci-separation 2000000
   <mcool::res> <expected.tsv>`: convolves HiCCUPS-style kernels (donut, lower-
   left, horizontal, vertical) over the O/E heatmap to find focal enrichments,
   applies Benjamini-Hochberg FDR per distance (lambda) bin, and clusters nearby
   significant pixels into loop calls (BEDPE).

## Method notes

- **Resolution**: 5–10 kb (loop anchors must span >1 bin and be statistically
  supported); too coarse misses dots, too fine is too sparse.
- **FDR per distance bin** controls the strong distance-dependence of contact
  frequency — a fixed global threshold would over-call short-range pixels.

## Dependencies

- CLI: cooltools
- Python: cooler, numpy, pandas

## References

- cooltools dots — https://cooltools.readthedocs.io/
- Rao et al. 2014 (HiCCUPS) — https://doi.org/10.1016/j.cell.2014.11.021
