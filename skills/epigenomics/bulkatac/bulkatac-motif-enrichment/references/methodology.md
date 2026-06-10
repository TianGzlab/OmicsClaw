# Methodology — bulkatac-motif-enrichment

## Capabilities

Bulk ATAC-seq ENCODE Step 5a — TF motif enrichment via HOMER
`findMotifsGenome.pl` (Heinz et al. 2010, *Mol Cell* 38(4):576-589).
Concretely:

- **Three-pronged enrichment** — runs HOMER on (a) the full consensus peak set, (b) DA-up peaks, (c) DA-down peaks. Each with the appropriate background.
- **Known-motif enrichment** — hypergeometric test of every PWM in HOMER's curated database against the peak foreground.
- **De novo motif discovery** — HOMER's iterative motif search to surface novel / experiment-specific PWMs not in the known database.
- **Per-peak-set background strategy** (see docstring `bulkatac-motif-enrichment.py:8-17`):
  - `all_peaks` → GC-matched random genomic regions (HOMER default). Question: "What motifs are enriched in open chromatin vs the genome?"
  - `da_up` / `da_down` → consensus peaks as background (`-bg consensus_peaks.bed -chopify`). Question: "What motifs drive *condition-specific* accessibility changes?"
- **Cross-peak-set summary** — `top_motif_summary.tsv` ranks motifs across all peak sets in a single table.
- **Top-motif bar plots** — PDF + PNG per peak set, top known + top de novo.

What this skill does NOT do (handed off elsewhere):

- TF binding occupancy → `bulkatac-footprinting` (different question: enrichment surfaces candidates, footprinting confirms in-vivo binding).
- TF gene-expression integration → manual; no skill yet.

## Workflow

1. **Check HOMER** — hard-fail if `findMotifsGenome.pl` is not on `PATH`.
2. **Resolve chain** — `--prev-result` must be a `bulkatac-DA` result; walk its `prev_result` key back to peak-calling for the consensus BED.
3. **Resolve genome** — `--genome` CLI override or auto-detected from Step 3 `sample_sheet.genome`.
4. **Resolve genome FASTA** — CLI override or 5-level fallback search (genome_files, Step-2 params, sibling `reference_<genome>*` dirs, mapping/step2/alignment sibling subdirs).
5. **Resolve DA BEDs** — pick up `up_bed` / `down_bed` from the DA `result.json`; either / both may be absent (silently skipped).
6. **Resolve HOMER parameters** — `--size` (int or `"given"`), `mask = --mask and not --no-mask`, `--denovo-length`, `--n-motifs`.
7. **Run HOMER per peak set** — `_lib.motif_enrichment.run_motif_enrichment_multi` handles the three calls with appropriate backgrounds + foreground BEDs.
8. **Summarise** — `write_motif_summary` builds `top_motif_summary.tsv`; `plot_top_known_motifs` / `plot_top_denovo_motifs` render the top-motif bar charts.
9. **Emit outputs** — `report.md`, `result.json`, `reproducibility/`, `README.md`, then stdout summary.

## Methodology — per-step details

### HOMER `findMotifsGenome.pl` invocation

Per peak set, the invocation looks like:

```
findMotifsGenome.pl <peaks.bed> <genome> <output_dir> \
    -size <size> [-mask] -len <denovo_length> -S <n_motifs> \
    [-bg <consensus_peaks.bed> -chopify] \
    -p <threads> [-fasta <genome_fasta>]
```

- **`<genome>`** is the genome short-name (`hg38`, `mm10`, `sacCer3`). HOMER ships per-genome data installed via `configureHomer.pl -install <genome>`; without it, the genome string is just metadata and `-fasta` is mandatory.
- **`-fasta <genome_fasta>`** bypasses the HOMER genome install — HOMER reads sequences directly. Slightly slower per run but removes the install dependency.
- **`-size <n>`** sets the per-peak window centered on the peak summit. `200` (HOMER default) means ±100 bp. `given` uses the peak's actual coordinates (recommended when peaks are narrow and summit-centered, as they are from MACS2).
- **`-mask`** enables soft-masking of repeats (default; recommended for mammals). Pass `--no-mask` for non-mammalian / non-vertebrate genomes (yeast, plants) where masking can discard too much sequence.
- **`-len <8,10,12>`** are the de novo motif lengths searched.
- **`-S <25>`** caps the number of de novo motifs reported.
- **`-p <threads>`** parallelises HOMER's de novo search; this is the main cost driver.

### Background strategy details

| Peak set | Foreground | Background | Why |
|---|---|---|---|
| `all_peaks` | Consensus peaks (all conditions union) | GC-matched random genomic regions (HOMER default) | Asks what motifs the experiment's open-chromatin landscape is enriched for vs the genome at large |
| `da_up` | DA-up subset BED | Consensus peaks (`-bg ... -chopify`) | Asks what motifs are *additionally* enriched in the gained-accessibility subset vs all open chromatin. Without this swap, the result just rediscovers generic open-chromatin motifs (AP-1, CTCF). |
| `da_down` | DA-down subset BED | Consensus peaks (`-bg ... -chopify`) | Symmetric to `da_up` for lost accessibility |

`-chopify` chops large background regions to the foreground peak size
so the foreground-vs-background length distribution is matched.

### HOMER's statistical model

- **Known motifs**: hypergeometric / ZOOPS scoring. Per motif, HOMER counts foreground peaks containing ≥ 1 occurrence vs background peaks containing ≥ 1, and reports the hypergeometric p-value.
- **De novo motifs**: HOMER's iterative motif search. Starts from k-mers over-represented in the foreground, expands to PWMs, and refines via expectation-maximisation. Reports the top `-S` motifs by p-value.
- **Autonormalization**: lower-order oligo autonormalization (`-nlen`) is on by default — corrects for short-oligo composition biases between foreground and background. Custom backgrounds (`-bg`) undergo the same normalization.
- **Multiple-testing correction**: HOMER reports Benjamini-Hochberg q-values alongside raw p-values in `knownResults.txt`. De novo p-values are not corrected (they're empirical against the foreground k-mer null).

### Top-motif plotting

`plot_top_known_motifs` and `plot_top_denovo_motifs` render the top-15
(known) and top-10 (de novo) motifs per peak set as horizontal bar
charts ranked by `-log10(p-value)`. Both PDF and PNG are emitted via
the shared `_save_figure` helper at `_lib/motif_enrichment.py:763` so
the bar charts work for both web preview and publication-ready insertion.

## Demo

This skill has NO `--demo` flag. Smoke-test via the full chain:

```bash
WD=/tmp/atac-demo
python skills/epigenomics/bulkatac/bulkatac-preprocessing/bulkatac-preprocessing.py --demo --wd $WD
python skills/epigenomics/bulkatac/bulkatac-mapping/bulkatac-mapping.py            --wd $WD
python skills/epigenomics/bulkatac/bulkatac-peak-calling/bulkatac-peak-calling.py  --wd $WD
python skills/epigenomics/bulkatac/bulkatac-DA/bulkatac-DA.py                       --wd $WD
python skills/epigenomics/bulkatac/bulkatac-motif-enrichment/bulkatac-motif-enrichment.py \
    --wd $WD --genome sacCer3 --no-mask
```

(`--no-mask` because sacCer3 is non-mammalian; `--genome` because the
demo's sacCer3 may not be installed in HOMER on every machine — pass
`--genome-fasta /refs/sacCer3.fa` if not.)

## Dependencies

**Python packages** (declared in SKILL.md `requires`):

- `pandas`, `numpy` — table I/O.
- `matplotlib` — top-motif bar charts.

**External tools** (must be on `PATH`; hard-checked via
`check_homer`):

- `findMotifsGenome.pl` (HOMER). Install with `conda install -c bioconda homer`.
- `configureHomer.pl` (HOMER's installer). Used manually to install per-genome data: `configureHomer.pl -install <genome>`. Not invoked by this script.

**Tested versions**: HOMER ≥ 4.11. Genome data: HOMER's per-genome
install OR a working FASTA passed via `--genome-fasta`.

## References

- Heinz S, et al. (2010). Simple combinations of lineage-determining
  transcription factors prime cis-regulatory elements required for macrophage
  and B cell identities (HOMER). *Mol. Cell* 38:576–589.
  <https://doi.org/10.1016/j.molcel.2010.05.004>
- HOMER motif-analysis documentation —
  <http://homer.ucsd.edu/homer/ngs/peakMotifs.html>
- ENCODE ATAC-seq pipeline — <https://www.encodeproject.org/atac-seq/>
