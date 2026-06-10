# Methodology — bulkchip-motif-enrichment

> Scaffold: methodology specified; tool-backed implementation pending.

## Capabilities

- HOMER known-motif enrichment + de novo discovery on a chosen ChIP peak subset.

Does not call peaks, annotate genes, or run differential binding (siblings).

## Workflow

1. **Resolve subset** — consensus / per-condition peaks (Step 3) or DA up/down
   peaks (`--de-result`, Step 4).
2. **HOMER** (`run_all_motif_enrichment`)
   - `findMotifsGenome.pl <peaks.bed> <genome> <out_dir> -size <size>
     -len <len> -p <threads>`.
   - `-size 200` centers a 200 bp window on summits (point-source default);
     `-size given` scans full intervals (broad marks).
   - Emits `knownResults.txt` (curated motif library enrichment) +
     `homerResults.html` (de novo motifs aligned to known TFs).
3. **Summary** — parse top known motifs (name, p-value, % targets vs background).

## Method notes

- **TF ChIP**: the ChIP'd factor's own motif should rank at/near the top — a
  primary quality signal for a successful TF ChIP.
- **Histone marks**: motifs reflect co-localized sequence-specific TFs, not a
  "mark motif"; interpret accordingly.
- HOMER background defaults to GC/length-matched genomic sequences.

## Demo

No implemented demo dataset yet (scaffold).

## Dependencies

- Python: pandas, numpy
- External: HOMER (`findMotifsGenome.pl`) + an installed HOMER genome package
  (see `0_setup_env_for_bulkchip.sh`)

## References

- HOMER motif analysis — http://homer.ucsd.edu/homer/motif/
- Heinz et al. 2010 (HOMER) — https://doi.org/10.1016/j.molcel.2010.05.004
