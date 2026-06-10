# Methodology — bulkhic-compartments

> Implemented (cooltools). See `_lib/compartments.py`.

## Capability

A/B compartments from a balanced `.mcool`: eigenvector decomposition (E1) +
saddle-plot strength.

## Workflow

1. **expected-cis** — `cooltools expected-cis` → diagonal-averaged contact
   frequency (observed/expected normalisation input for saddle).
2. **GC phasing track** — `bioframe.frac_gc` over the cooler bins → per-bin GC%
   (used to orient the eigenvector so + = A / − = B).
3. **eigs-cis** — `cooltools eigs-cis --phasing-track <GC> --n-eigs 1` → E1
   eigenvector per bin (`*.cis.vecs.tsv`) + eigenvalues (`*.cis.lam.txt`).
4. **A/B BED** — binarise E1: > 0 → A, < 0 → B.
5. **saddle** — `cooltools saddle` bins the genome by E1 quantile and tabulates
   mean O/E contacts between bin pairs → a 2D compartment-strength matrix +
   heatmap (strong A-A and B-B, depleted A-B).

## Method notes

- **Resolution**: 100 kb–1 Mb. Compartments are a coarse, megabase-scale feature.
- **Phasing**: the eigenvector sign is mathematically arbitrary; GC content
  (a proxy for gene density / activity) fixes A = positive.

## Dependencies

- CLI: cooltools
- Python: cooler, bioframe, numpy, pandas, matplotlib

## References

- cooltools eigs-cis / saddle — https://cooltools.readthedocs.io/
- Lieberman-Aiden et al. 2009 (A/B compartments) — https://doi.org/10.1126/science.1181369
