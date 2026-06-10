---
doc_id: bulkatac-DA-guardrails
title: Bulk ATAC Differential Accessibility Guardrails
doc_type: knowhow
critical_rule: MUST verify a bulkatac-peak-calling result.json with a ≥2-condition sample sheet is chained in, explain the contrast and padj/lfc cuts before running, and never call significance on the raw p-value — direction is always set on the BH-adjusted padj
domains: [epigenomics]
related_skills: [bulkatac-DA, bulkatac-da, bulkatac-differential-accessibility]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ATAC differential accessibility, pyDESeq2, DESeq2, volcano plot, consensus peak counts, IGV BED tracks, 差异可及性]
priority: 1.0
---

# Bulk ATAC Differential Accessibility Guardrails

- **Inspect first**: confirm a Step-3 `peak_calling/result.json` (carrying `consensus.count_matrix`) is resolvable via `--prev-result` (alias `--input`) or sibling-detection; the run hard-fails if fewer than two conditions exist in the sample sheet. There is no `--demo` flag.
- **Do not overclaim scope**: this skill runs a single two-group pyDESeq2 contrast only — it does NOT support multi-factor / ANOVA designs, covariates, batch / paired designs, time-course modelling, or LFC shrinkage; it does not do motif enrichment or footprinting.
- **Explain the run before execution**: state the resolved `--treat` / `--control` (auto-picks the two alphabetically-first conditions when omitted), `--padj` (default 0.05), and `--lfc` (default 1.0); for 3+ conditions only one pair is tested — pass both flags to control it.
- **Use wrapper-correct language**: `log2FoldChange` is unshrunk (fine for the padj/lfc cut, not for ranking); significance is always called on `padj` (Benjamini-Hochberg), never the raw `pvalue`; the annotation join is silent on miss — check `result.json["da"]["annotation_source"]`.
- **Preserve the contract**: successful runs emit `report.md`, `result.json`, and under `DA/<contrast>/<param_tag>/` the `da_results_<contrast>.tsv`, `da_summary_<contrast>.csv`, and three IGV-ready BEDs (`da_peaks_{up,down,all}`); the volcano (`pdf`/`png`/`tsv`) lands under `plots/<contrast>/<param_tag>/`.
- **Interpret outputs correctly**: BED up-peaks are red `(255,0,0)`, down-peaks blue `(0,0,255)`; peaks with `NA` padj (DESeq2 independent filtering) are labelled `ns`; re-running with new `--padj`/`--lfc` writes parallel trees, not overwrites.
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkatac-DA.md`.
