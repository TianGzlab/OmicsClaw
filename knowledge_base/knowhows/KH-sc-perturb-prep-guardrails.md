---
doc_id: sc-perturb-prep-guardrails
title: Single-Cell Perturbation Preparation Guardrails
doc_type: knowhow
critical_rule: MUST explain that this skill merges upstream sgRNA assignments into expression data and does not infer guide identities from raw FASTQ by itself
domains: [singlecell]
related_skills: [sc-perturb-prep]
phases: [before_run, after_run]
search_terms: [perturbation prep, sgRNA assignment, perturb-seq, CROP-seq, guide mapping]
priority: 1.0
source_urls:
  - https://www.10xgenomics.com/support/software/cell-ranger/7.2/analysis/running-pipelines/cr-feature-bc-analysis
  - https://pertpy.readthedocs.io/en/latest/api/tools/pertpy.tools.Mixscape.html
---

# Single-Cell Perturbation Preparation Guardrails

- **Inspect first**: confirm whether the user already has a barcode-to-guide assignment table; if not, say clearly that this skill cannot assign guides from raw FASTQ by itself.
- **Do not fabricate perturbation labels**: controls, target genes, and sgRNA identities must come from the mapping file or explicit user rules.
- **Keep modalities separated**: when 10x feature-barcode data include non-gene features, export a gene-expression-only AnnData for downstream scRNA analysis and report what was removed.
- **Handle multi-guide cells honestly**: dropping or keeping multi-guide cells changes the downstream interpretation; record that decision explicitly.
- **For longer tuning and interpretation guidance**: see `knowledge_base/skill-guides/singlecell/sc-perturb-prep.md`.
