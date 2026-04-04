---
doc_id: skill-guide-sc-standardize-input
title: OmicsClaw Skill Guide — SC Standardize Input
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-standardize-input]
search_terms: [single-cell standardize input, AnnData contract, counts layer, gene symbols, metadata checks]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Standardize Input

**Status**: implementation-aligned guide for the current `sc-standardize-input`
wrapper. It explains what the skill can standardize automatically and what must
still be confirmed with the user before downstream analysis.

## Purpose

Use this guide when you need to decide:

- whether a user-provided single-cell object should be standardized before any downstream skill
- which expression source should become the canonical count matrix
- when standardization is enough and when you still must stop for missing biological metadata

## Step 1: Decide Whether To Standardize First

Treat this skill as the explicit export/debug wrapper around the shared
single-cell canonicalization helper. Use it when:

- the user uploads an external `.h5ad` from outside OmicsClaw
- raw counts may live in `layers['counts']` or `adata.raw` instead of `adata.X`
- `var_names` are Ensembl IDs, feature IDs, or otherwise not ideal for downstream symbol matching
- the next requested skill is sensitive to count-vs-normalized state

If the input is already an OmicsClaw-standardized `h5ad`, you usually do not need to rerun this step. Many downstream scRNA skills should canonicalize compatible inputs automatically.

## Step 2: What The Skill Standardizes Automatically

Current wrapper behavior:

1. inspect the best available count-like source in this order:
   - `layers['counts']`
   - aligned `adata.raw`
   - `adata.X`
2. choose the best available gene symbol source:
   - `var_names`
   - or metadata columns such as `gene_symbols`, `gene_name`, `feature_name`
3. make `obs_names` and `var_names` unique
4. write the canonical count matrix into both:
   - `adata.X`
   - `adata.layers['counts']`
5. write a count-like snapshot into:
   - `adata.raw`
6. record provenance and state in:
   - `adata.uns['omicsclaw_input_contract']`
   - `adata.uns['omicsclaw_matrix_contract']`
7. save `processed.h5ad`

## Step 3: What The Skill Does Not Invent

This skill does **not** invent:

- sample / replicate metadata
- batch labels
- cluster or cell-type labels
- group comparison intent
- reference atlases or annotation models
- spliced / unspliced layers for velocity

If a downstream analysis depends on these and they are absent, stop and ask the user rather than pretending the standardized object is fully analysis-ready.

## Step 4: When To Stop And Ask The User

Stop and ask when:

- `species` matters biologically and the naming convention is ambiguous
- several plausible `groupby` / `batch_key` / `cluster_key` / `cell_type_key` columns exist
- the requested task needs metadata that is missing entirely
- the user asks a formal question, but the object only supports an exploratory first pass

Examples:

- `sc-de` pseudobulk without `sample_key`
- `sc-cell-communication` without cell-type labels
- `sc-batch-integration` without a true batch column
- `sc-cell-annotation` without a usable model/reference choice
- `sc-velocity` without `spliced` and `unspliced` layers

## Step 5: What To Tell The User After Standardization

A good post-run summary should say:

- where counts came from
- where gene symbols came from
- whether any warnings were emitted
- that `processed.h5ad` is now the canonical count-like object for downstream scRNA skills
- that this still does **not** mean normalized-expression skills are ready; methods expecting log-normalized expression usually need `sc-preprocessing` next

## Step 6: Downstream Decision Rule

After standardization:

- proceed automatically when the downstream skill has a safe first-pass default and all required data content exists
- ask for confirmation when key scientific parameters are ambiguous
- stop and ask for more metadata when the data cannot support the requested question
