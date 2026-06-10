# Methodology — bulkatac-DA

## Capabilities

Bulk ATAC-seq ENCODE Step 4a — differential accessibility on the
consensus peak set. Concretely:

- **pyDESeq2 GLM** on raw featureCounts (no manual normalisation — DESeq2 size factors are computed internally).
- **Two-group contrast** (`treat` over `control`): auto-detected from the upstream sample sheet's conditions, or set explicitly via `--treat` / `--control`.
- **Per-peak direction calls** (`up` / `down` / `ns`) at user-set `--padj` and `--lfc` cuts.
- **Annotation join** — merges the Step 3 `annotated_peaks.tsv` onto the results so each DA peak gets a nearest-gene / feature-category label without re-running annotation.
- **Volcano plot** — PDF + PNG + underlying point TSV.
- **IGV-ready BED tracks** — up / down / all DA peaks with track headers and per-peak RGB colours.
- **Idempotent checkpoint** — `_lib.DA.run_differential_accessibility` short-circuits when the per-contrast `da_results_*.tsv`, `da_summary_*.csv`, and `da_peaks_up_*.bed` already exist (`_lib/DA.py:149-152`); useful for re-rendering volcanos without re-fitting.

What this skill does NOT do (handed off elsewhere):

- More-than-two-group contrasts (e.g. ANOVA-style multi-factor designs) — run pyDESeq2 directly outside the skill.
- Time-course modelling — needs custom design matrices not exposed here.
- Motif enrichment in DA peaks → `bulkatac-motif-enrichment` (consumes the BED outputs).
- TF activity inference → `bulkatac-footprinting` on the consensus BAMs.

## Workflow

1. **Locate Step-3 result** — `--prev-result` explicit, else `<wd>/peak_calling/result.json`.
2. **Reconstruct upstream state** — count matrix path (`consensus.count_matrix`), sample names + conditions (`sample_sheet.samples`), Step-3 `qvalue`, and the auto-detected annotation TSV.
3. **Resolve contrast** — explicit `--treat`/`--control` or `(sorted_conditions[0], sorted_conditions[1])`. Hard-fail if fewer than two conditions.
4. **Derive `param_tag`** — `q<peak_qvalue>_padj<padj>_lfc<lfc>`.
5. **`run_differential_accessibility`** (`_lib/DA.py`) — load count matrix, run pyDESeq2, label `direction`, merge annotation, write `da_results_*.tsv` + `da_summary_*.csv` + three BED tracks.
6. **`plot_volcano`** (`_lib/DA.py:257`) — render PDF + PNG + underlying TSV from the results file.
7. **Emit outputs** — `report.md`, `result.json`, `reproducibility/`, `README.md`, then stdout summary.

## Methodology — per-step details

### pyDESeq2 model

- **Design matrix**: `~ condition` (single fixed effect). The wrapper does not currently expose covariates — for batch / paired designs, fork the script and pass the augmented design directly to `pyDESeq2`.
- **Count input**: raw integer counts from `featureCounts` (`peak_counts.txt`). PE counts are fragment-level (`--countReadPairs` was set in Step 3), which is what the negative-binomial GLM expects.
- **Pre-filter**: pyDESeq2's default low-count filter applies; `n_tested` in the summary reports the post-filter peak count, not the input row count.
- **Fold-change**: `log2FoldChange` is **unshrunk** — suitable for hypothesis testing against `--padj` / `--lfc` cuts but not for ranking. For shrinkage (apeglm / ashr), re-run pyDESeq2 directly on the count matrix.
- **Multiple-testing correction**: Benjamini–Hochberg (DESeq2 default).
- **Direction labels** (`_lib/DA.py:184-186`):
  - `up` if `padj < --padj` AND `log2FoldChange ≥ --lfc`
  - `down` if `padj < --padj` AND `log2FoldChange ≤ -lfc`
  - `ns` otherwise
- Peaks with `NA` padj (filtered out by DESeq2 independent filtering) are labelled `ns` and counted in `n_ns`.

### Contrast auto-detection

When `--treat` / `--control` are both omitted, the wrapper sorts the
unique condition labels alphabetically and assigns:

```
control = sorted(conditions)[0]
treat   = sorted(conditions)[1]
```

For three or more conditions only this single contrast is tested.
Pass `--treat` / `--control` explicitly to run any specific pair.

### Annotation join

The Step-3 annotation TSV is located at
`<step3>/annotation/qvalue<q>/annotated_peaks.tsv` (where `<q>` is the
Step-3 `qvalue`). The merge is on the consensus peak ID (`consensus_peak_<N>`)
which is stable across Step 3 → Step 4.

When the file is absent (annotation was skipped in Step 3, or no GTF /
HOMER was available), the join is silently skipped with a warning;
results still emit but without the `gene_name` / `feature_category` /
HOMER columns.

`--skip-annotation` forces the skip even when the file exists — useful
for fast re-runs.

### IGV BED track scheme

- BED9 with a `track name=... itemRgb="On"` header line.
- Up peaks: RGB `255,0,0` (red).
- Down peaks: RGB `0,0,255` (blue).
- "All" BED merges both, preserving direction colour. Useful for a single-track overview.

The peak `name` field is the consensus peak ID; `score` is `min(int(-10 * log10(padj)), 1000)`.

### Volcano plot

- `-log10(padj)` on the y-axis. Up / down / ns are classified by `padj` (BH-adjusted p-value) + the `--lfc` cut — the **same statistic** as the run summary, `report.md`, and the BED tracks, so the figure legend always matches the text. Raw `pvalue` is never used for the significance call: across thousands of peaks it is not multiple-testing-corrected (cf. ENCODE, which likewise relies on corrected statistics, not raw p).
- Threshold guides: a horizontal dashed line at `-log10(--padj)` and vertical dashed lines at `±--lfc`.
- Points coloured by `direction`. Peaks with `padj == 0` (below DESeq2's machine precision) are floored to the smallest non-zero `padj` in the data and drawn as triangles, so truncation is visible rather than hidden at an arbitrary y cap.
- Underlying point data are written to `volcano_<contrast>.tsv` (columns include both `pvalue` and `padj`) for downstream re-plotting.

## Demo

This skill has NO `--demo` flag. Smoke-test via the full chain:

```bash
WD=/tmp/atac-demo
python skills/epigenomics/bulkatac/bulkatac-preprocessing/bulkatac-preprocessing.py --demo --wd $WD
python skills/epigenomics/bulkatac/bulkatac-mapping/bulkatac-mapping.py            --wd $WD
python skills/epigenomics/bulkatac/bulkatac-peak-calling/bulkatac-peak-calling.py  --wd $WD
python skills/epigenomics/bulkatac/bulkatac-DA/bulkatac-DA.py                       --wd $WD
```

The demo yields the T15 vs T0 osmotic-stress contrast on sacCer3.

## Dependencies

**Python packages** (declared in SKILL.md `requires`):

- `pandas` — table I/O.
- `numpy` — transitive.

**External Python packages** (must be importable; not declared in
`requires` because they're implicit transitive of pyDESeq2 / matplotlib):

- `pydeseq2` — the DESeq2 GLM implementation.
- `matplotlib` — volcano rendering.

**External tools** (must be on `PATH`):

- None. This skill is pure Python — no shelling out.

**Tested versions**: pydeseq2 ≥ 0.5, pandas ≥ 1.5, matplotlib ≥ 3.6.

## References

Methods and the rationale for calling significance on the **adjusted**
p-value (`padj`, BH-FDR) rather than the raw p-value:

- Love MI, Huber W, Anders S (2014). Moderated estimation of fold change
  and dispersion for RNA-seq data with DESeq2. *Genome Biology* 15:550.
  <https://doi.org/10.1186/s13059-014-0550-8> — negative-binomial GLM +
  Wald test; reports BH-adjusted `padj`.
- Benjamini Y, Hochberg Y (1995). Controlling the false discovery rate.
  *J. R. Stat. Soc. B* 57:289–300.
  <https://doi.org/10.1111/j.2517-6161.1995.tb02031.x> — the BH procedure
  behind `padj`; multiple-testing correction is required across the
  thousands of peaks tested here.
- Muzellec B, Telenczuk M, Cabeli V, Andreux M (2023). PyDESeq2: a Python
  package for bulk RNA-seq differential expression analysis. *Bioinformatics*.
  <https://github.com/owkin/PyDESeq2> — the DESeq2 implementation used.

ATAC-seq differential-accessibility practice — significance is called on
FDR / `padj`, never raw p:

- Gontarz P, et al. (2020). Comparison of differential accessibility
  analysis strategies for ATAC-seq data. *Scientific Reports* 10:10150.
  <https://doi.org/10.1038/s41598-020-66998-4>
- Reske JJ, Wilson MR, Chandler RL (2020). ATAC-seq normalization method
  can significantly affect differential accessibility analysis and
  interpretation. *Epigenetics & Chromatin* 13:22. PMID 32321567.
- ENCODE ATAC-seq pipeline — <https://www.encodeproject.org/atac-seq/> —
  peak significance/reproducibility via IDR (a corrected statistic), not
  raw p-value cutoffs.

Reference pipelines surveyed for convention:

- CebolaLab ATAC-seq — <https://github.com/CebolaLab/ATAC-seq>
- nf-core/chipseq — <https://github.com/nf-core/chipseq>
