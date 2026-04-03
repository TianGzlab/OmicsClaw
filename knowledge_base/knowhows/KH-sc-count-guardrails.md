---
doc_id: sc-count-guardrails
title: Single-Cell Count Guardrails
doc_type: knowhow
critical_rule: MUST distinguish raw FASTQ counting from importing existing Cell Ranger or STARsolo outputs, and must not overstate current protocol support
domains: [singlecell]
related_skills: [sc-count]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell counting, Cell Ranger count, STARsolo, feature-barcode matrix, 10x, 单细胞计数]
priority: 1.0
source_urls:
  - https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/running-pipelines/cr-gex-count
  - https://www.10xgenomics.com/support/software/cell-ranger/latest/analysis/outputs/cr-outputs-gex-overview
  - https://github.com/alexdobin/STAR/blob/master/docs/STARsolo.md
  - https://nf-co.re/scrnaseq/dev/docs/usage
---

# Single-Cell Count Guardrails

- **Separate import from execution**: if the user already has a completed Cell Ranger or STARsolo output directory, import and standardize it; do not ask for a reference index or rerun the backend unnecessarily.
- **Keep protocol support honest**: the current wrapper focuses on mainstream 10x-style droplet workflows. Do not imply full support for Smart-seq, Drop-seq, inDrops, Parse, or other custom barcode geometries.
- **Do not overstate Cell Ranger coverage**: upstream `cellranger count` can also handle Feature Barcode modes, but the current OmicsClaw wrapper is intentionally scoped to the core count workflow and stable matrix import path.
- **Use STARsolo conservatively**: require an explicit supported chemistry (`10xv2`, `10xv3`, `10xv4`) for real FASTQ-backed STARsolo runs unless the user is importing an existing STARsolo output.
- **Be careful with whitelist language**: STARsolo whitelist auto-detection is best-effort only; if the correct whitelist is not obvious, ask for it or stop clearly rather than guessing.
- **Preserve upstream artifacts for downstream skills**: raw `.h5` outputs matter for CellBender-like ambient correction, and BAM / Velocyto outputs matter for RNA velocity preparation.
- **Explain the hand-off artifact**: `standardized_input.h5ad` is the downstream OmicsClaw contract, but it does not mean all upstream backend details have been discarded.
- **For detailed operator guidance**: see `knowledge_base/skill-guides/singlecell/sc-count.md`.
