---
doc_id: sc-multi-count-guardrails
title: Single-Cell Multi Count Guardrails
doc_type: knowhow
critical_rule: MUST distinguish preserved multimodal outputs from the RNA-only handoff, and must not pretend current downstream scRNA skills are fully multimodal-aware
domains: [singlecell]
related_skills: [sc-multi-count]
phases: [before_run, on_warning, after_run]
search_terms: [cellranger multi, CITE-seq, HTO, hashing, multimodal count, 单细胞多模态计数]
priority: 1.0
source_urls:
  - https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/outputs/cr-3p-outputs-cellplex
  - https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/outputs/cr-outputs-overview
---

# Single-Cell Multi Count Guardrails

- **Explain the two outputs clearly**: `multimodal_standardized_input.h5ad` preserves all feature types, while `rna_standardized_input.h5ad` is the current bridge to most existing scRNA downstream skills.
- **Do not overstate multimodal downstream coverage**: current single-cell downstream skills in OmicsClaw remain largely RNA-first even when multimodal inputs are preserved.
- **Separate import from execution**: if the user already has a completed `cellranger multi` run, import it instead of rerunning the backend.
- **Handle `per_sample_outs/` carefully**: if multiple per-sample outputs exist, require an explicit `--sample` when the user wants one sample-specific handoff.
- **Preserve feature types honestly**: ADT / antibody and multiplexing capture features should remain labeled through `feature_types`, not silently dropped in the multimodal object.
- **Do not fake multimodal normalization**: this skill counts and standardizes; it does not perform RNA + ADT joint normalization or multimodal WNN-style downstream analysis.
- **For detailed operator guidance**: see `knowledge_base/skill-guides/singlecell/sc-multi-count.md`.
