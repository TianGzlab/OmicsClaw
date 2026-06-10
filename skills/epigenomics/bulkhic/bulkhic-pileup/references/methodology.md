# Methodology — bulkhic-pileup

> Implemented (cooltools). See `_lib/pileup.py`.

## Capability

Aggregate (pileup / APA) signal around a feature set from a balanced `.mcool`.

## Workflow

1. **expected-cis** — `cooltools expected-cis` (observed/expected normalisation).
2. **pileup** — `cooltools pileup --features-format <bedpe|bed> --flank <bp>
   --expected <expected.tsv> <mcool::res> <features>`: extracts a 2D O/E snippet
   centered on each feature (off-diagonal for BEDPE loops → APA; on-diagonal for
   BED boundaries) and averages them.
3. **Plot + score** — mean heatmap; central-pixel enrichment = mean(center 3×3) /
   mean(corner) as a single-number loop/boundary strength.

## Method notes

- **APA** (Aggregate Peak Analysis) on loops: a strong central focus relative to
  the corners indicates collectively real loops.
- **coolpup.py** is the memory-efficient streaming alternative (and adds trans
  pileups) for very large feature sets.

## Dependencies

- CLI: cooltools (coolpup.py optional)
- Python: cooler, numpy, pandas, matplotlib

## References

- cooltools pileup — https://cooltools.readthedocs.io/
- coolpuppy — https://github.com/open2c/coolpuppy
