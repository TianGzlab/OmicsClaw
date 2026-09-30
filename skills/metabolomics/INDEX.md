# Metabolomics — Skill Index

> The skill list below is derived from each skill's `SKILL.md` frontmatter
> and is checked by `tests/skills/test_domain_index_is_current.py`.
> Regenerate it with
> `OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py`.
> The prose above the list is written by hand.

**Domain key:** `metabolomics`

**Skill count:** 8

**Primary data types:** mzml, cdf, csv

LC-MS metabolomics: XCMS preprocessing, peak detection, metabolite annotation (SIRIUS/GNPS), normalization, DE, pathway enrichment.

## Skills

- `metabolomics-annotation` — Load when annotating LC-MS features against a built-in 15-metabolite HMDB demo dictionary by m/z within a `--ppm` tolerance — emits a per-feature annotation table. Skip when needing real HMDB / KEGG / LipidMaps / METLIN look-up (this skill is demo-only); raw spectra (use metabolomics-xcms-preprocessing).
  triggers: metabolite annotation, SIRIUS, GNPS, MetFrag, spectral matching, metabolite ID, ppm tolerance
- `metabolomics-de` — Load when running two-group metabolomics DE (t-test + log2FC + BH-FDR + PCA) on a feature × sample CSV using `--group-a-prefix` / `--group-b-prefix` (default `ctrl` / `treat`). Skip when needing tunable test backends (use metabolomics-statistics); raw spectra.
  triggers: metabolomics differential, PLS-DA, volcano plot, biomarker, OPLS-DA
- `metabolomics-normalization` — Load when normalising a feature × sample metabolomics CSV via median, quantile, total (sum), PQN (probabilistic quotient), or log methods — emits a normalised wide-form table. Skip when also imputing (use metabolomics-quantification); raw spectra (use metabolomics-xcms-preprocessing).
  triggers: metabolomics normalization, scaling, NOREVA, TIC normalization
- `metabolomics-pathway-enrichment` — Load when running over-representation analysis (ORA) on a metabolite list via Fisher's exact test against a built-in 9-pathway DEMO dictionary, BH-FDR adjusted. Skip when needing real KEGG / Reactome (this skill is demo-only); `mummichog` / `fella` topology methods (CLI accepts them but only ORA runs).
  triggers: metabolomics pathway, KEGG, MetaboAnalyst, enrichment, mummichog
- `metabolomics-peak-detection` — Load when running per-sample peak picking on a feature × intensity table via `scipy.signal.find_peaks` — emits per-(sample, feature) detected peaks with prominence and width. Skip when working with mz / RT raw scans (use metabolomics-xcms-preprocessing); only normalising / quantifying (use metabolomics-quantification).
  triggers: peak detection, feature detection, XCMS, MZmine, MS-DIAL, peak picking
- `metabolomics-quantification` — Load when imputing missing values (min / median / KNN) and normalising (TIC / median / log) a feature × sample metabolomics CSV. Skip when only normalisation is needed (use metabolomics-normalization); the input is raw spectra (use metabolomics-xcms-preprocessing).
  triggers: metabolomics quantification, imputation, feature quantification, missing values
- `metabolomics-statistics` — Load when running univariate two-group testing (t-test / Wilcoxon / ANOVA / Kruskal-Wallis) on a feature × sample metabolomics CSV with `--group1-prefix` / `--group2-prefix` column matching, BH-FDR adjusted. Skip when working with raw spectra (use metabolomics-xcms-preprocessing); two-group DE with default `ctrl` / `treat` prefixes (use metabolomics-de).
  triggers: metabolomics statistics, multivariate, PCA, clustering
- `metabolomics-xcms-preprocessing` — Load when running an XCMS-style preprocessing summary on LC-MS metabolomics raw / vendor-converted files — emits a peak table with m/z, retention time, and per-sample intensities. Skip when working with an already-built peak table (use metabolomics-peak-detection); only annotation is needed (use metabolomics-annotation).
  triggers: xcms, metabolomics preprocessing, LC-MS, peak detection, RT alignment
