# Methodology — bulkhic-insulation

> Implemented (cooltools). See `_lib/insulation.py`.

## Capability

TAD boundaries from a balanced `.mcool` via the diamond insulation score.

## Workflow

1. **insulation** — `cooltools insulation --threshold Li --bigwig <mcool::res>
   <window…>`: slides a diamond window along the diagonal, summing contacts that
   cross each bin; local minima of the score mark insulating boundaries.
2. **Boundary calling** — boundaries are minima whose topographic *prominence*
   exceeds an automated (Li/Otsu image-thresholding) or fixed cutoff; emitted as
   `is_boundary_<window>` + `boundary_strength_<window>` columns.
3. **BED export** — boundary bins → BED4 (chrom, start, end, strength).

## Method notes

- **Resolution / window**: 10–50 kb bins; window ≈ 10× the bin size (rule-of-thumb).
- **Output tracks**: bigWig insulation tracks per window for genome-browser viewing.

## Dependencies

- CLI: cooltools
- Python: cooler, numpy, pandas

## References

- cooltools insulation — https://cooltools.readthedocs.io/
- Crane et al. 2015 (insulation score) — https://doi.org/10.1038/nature14450
