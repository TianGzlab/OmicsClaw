---
doc_id: skill-guide-sc-grn
title: OmicsClaw Skill Guide — SC GRN
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-grn]
search_terms: [GRN, pySCENIC, regulon, TF list, motif database, AUCell, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC GRN

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-grn` skill. This guide focuses on the current pySCENIC-style wrapper and
its real resource requirements.

## Purpose

Use this guide when you need to decide:
- whether the user has the external resources needed for a real GRN run
- which parameters matter most in the current wrapper
- how to explain pySCENIC stages without pretending they are one monolithic step

## Step 1: Inspect The Data First

Key properties to check:
- **Expression state**:
  - preprocessed expression matrix is expected
- **External resources**:
  - TF list
  - motif annotation file
  - cisTarget / ranking database files
- **Compute budget**:
  - GRNBoost2 can be expensive on large matrices

Important implementation notes in current OmicsClaw:
- the public workflow is effectively `pyscenic_workflow`
- the wrapper covers GRNBoost2, motif pruning, and AUCell scoring
- `n_top_targets` is mainly a wrapper export cap, not a pySCENIC core algorithm knob

## Step 2: Pick The Method Deliberately

Current OmicsClaw exposes one GRN workflow:

| Workflow | Best first use | Main caveat |
|----------|----------------|-------------|
| **pyscenic_workflow** | Full regulon analysis when required resources are available | Not self-contained; external databases are mandatory |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run GRN inference
  Workflow: pyscenic_workflow
  Parameters: tf_list=tfs.txt, db=*.feather, motif=motifs.tbl, n_jobs=8
  Note: this workflow requires external pySCENIC resources and will not auto-download them.
```

## Step 4: Method-Specific Tuning Rules

Tune in this order:
1. `tf_list`
2. `db`
3. `motif`
4. `n_jobs`
5. `seed`

Guidance:
- treat `tf_list`, `db`, and `motif` as core scientific inputs, not optional extras
- use `n_jobs` for runtime scaling
- use `seed` when reproducibility matters across repeated runs

Important warnings:
- do not pretend the wrapper exposes the full pySCENIC CLI parameter surface
- do not say the workflow can run meaningfully without database resources

## Step 5: What To Say After The Run

- If no regulons are found: check TF list coverage and motif database compatibility first.
- If runtime is excessive: mention `n_jobs` and resource size before changing biology-facing assumptions.
- If AUCell activity looks sparse: explain that resource mismatch can matter as much as model quality.

## Step 6: Explain Outputs Using Method-Correct Language

- describe adjacencies as candidate TF-target co-expression edges
- describe regulons as motif-pruned TF target sets
- describe AUCell scores as per-cell regulon activity estimates

## Official References

- https://pyscenic.readthedocs.io/en/latest/tutorial.html
- https://pyscenic.readthedocs.io/en/latest/installation.html
- https://github.com/aertslab/pySCENIC
- https://arboreto.readthedocs.io/en/latest/userguide.html

