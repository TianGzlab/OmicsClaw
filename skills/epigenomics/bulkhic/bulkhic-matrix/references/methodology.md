# Methodology — bulkhic-matrix

> Implemented (cooler + cooltools). See `_lib/matrix.py`.

## Capability

`.pairs` → ICE-balanced, multi-resolution `.cool`/`.mcool` + P(s) QC (+ optional `.hic`).

## Workflow

1. **cload** — `cooler cload pairs -c1 2 -p1 3 -c2 4 -p2 5 --assembly <genome>
   <chrom.sizes>:<base_binsize> <pairs.gz> <base.cool>`. The column indices are
   the pairtools `.pairs` default (chrom1=2, pos1=3, chrom2=4, pos2=5).
2. **balance** — `cooler balance --mad-max 5 <base.cool>` (ICE matrix balancing;
   stores per-bin `weight`, excludes coverage outliers >5 MAD).
3. **zoomify** — `cooler zoomify --balance -r <resolutions> -o <mcool> <base.cool>`
   (each resolution must be a multiple of the base binsize; every level balanced).
4. **P(s)** — `cooltools expected-cis` at the QC resolution → diagonal-averaged
   contact frequency; plotted log-log (the foundational decay curve, and the
   observed/expected input for compartments / dots).
5. **.hic (optional)** — convert `.pairs` → juicer "short" format (strand chr pos
   frag) → `java -jar juicer_tools pre`. Requires Java + jar; any failure logs a
   warning and is skipped (cooler outputs unaffected).

## Method notes

- **Default resolutions**: 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000 kb — covers
  loops (5–10 kb) through compartments (100 kb–1 Mb).
- **ICE balancing** removes multiplicative bias (depth, mappability, GC) so the
  expected genome-wide contact frequency is ~1; all cooltools analyses assume a
  balanced matrix (`weight` column).
- **Why cooler-primary, .hic-optional**: cooler/cooltools is the analysis path
  (Python, CPU); `.hic` is a visualization convenience for Juicebox.

## Dependencies

- CLI: cooler, cooltools; Java + juicer_tools.jar (optional, for `.hic`)
- Python: numpy, pandas, matplotlib

## References

- cooler — https://cooler.readthedocs.io/
- cooltools expected-cis — https://cooltools.readthedocs.io/
- juicer_tools pre — https://github.com/aidenlab/juicer/wiki/Pre


## Reproducibility QC (matrix_QC), when >=2 replicates

Two complementary per-resolution views (resolutions via `--scc-resolutions`; default
5000,10000,50000,100000):

- **SCC heatmap** (`matrix_QC/scc/<res>/`) - pairwise HiCRep stratum-adjusted correlation
  (`hicrep --h <auto = round(200000/res)> --dBPMax 500000`), seaborn clustermap.
  Source: Yang et al., Genome Res 2017 (HiCRep); Lin et al., Bioinformatics 2021 (HiCRep.py).
- **Sample PCA** (`matrix_QC/pca/<res>/`) - PCA (numpy SVD) on each sample's flattened balanced
  cis contacts within 500 kb over main chromosomes (>=1 Mb); PC1/PC2 scatter coloured by condition.
  Source: scHiCluster contact-matrix PCA embedding (Zhou et al., PNAS 2019, doi:10.1073/pnas.1901423116).
