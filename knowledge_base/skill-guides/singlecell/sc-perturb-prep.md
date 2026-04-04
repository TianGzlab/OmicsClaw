---
doc_id: skill-guide-sc-perturb-prep
title: OmicsClaw Skill Guide — SC Perturb Prep
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-perturb-prep]
search_terms: [perturbation prep, sgRNA assignment, perturb-seq, CROP-seq, guide mapping]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Perturb Prep

## Purpose

Use this guide to decide:
- whether the user already has enough upstream assignment information to prepare a perturbation-ready AnnData
- how to merge barcode-to-guide mappings into expression data safely
- when to stop and send the user back to Cell Ranger / CROP-seq upstream processing

## Method Selection

| Method | Best first use | Main caveat |
|---|---|---|
| **mapping_tsv** | expression AnnData plus a barcode-to-sgRNA mapping table | cannot recover guide identities from raw FASTQ on its own |

## Tune In This Order

1. `mapping_file`
2. `barcode_column`
3. `sgrna_column`
4. `target_column`
5. `control_patterns`
6. `keep_multi_guide`

## Interpretation

- The main success criterion is a clean `adata.obs` with perturbation labels, sgRNA IDs, and target genes that downstream `sc-perturb` can trust.
- The output should be limited to gene-expression features when the input contains CRISPR Guide Capture or other non-RNA feature types.
- Multi-guide cells are a design choice, not a technical nuisance; keeping them or dropping them changes the biological interpretation.

## Official References

- https://www.10xgenomics.com/support/software/cell-ranger/7.2/analysis/running-pipelines/cr-feature-bc-analysis
- https://www.sc-best-practices.org/conditions/perturbation_modeling.html
