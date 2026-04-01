---
doc_id: skill-guide-sc-cell-communication
title: OmicsClaw Skill Guide — SC Cell Communication
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-cell-communication]
search_terms: [cell communication, ligand receptor, LIANA, CellChat, groupby, species, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Cell Communication

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-cell-communication` skill. This guide explains the current wrapper surface
and does not imply the full LIANA or CellChat parameter set is exposed.

## Purpose

Use this guide when you need to decide:
- whether the current cell-type labels are good enough for communication analysis
- which backend is the best first pass
- how to explain grouping and species settings correctly

## Step 1: Inspect The Data First

Key properties to check:
- **Grouping column**:
  - `cell_type_key` must hold biologically meaningful labels
- **Species context**:
  - species affects ligand-receptor resource interpretation
- **Expression representation**:
  - raw vs normalized state matters differently across backends

Important implementation notes in current OmicsClaw:
- public methods are `builtin`, `liana`, and `cellchat_r`
- `cell_type_key` is the most important scientific parameter in the wrapper
- the built-in path is a lightweight OmicsClaw baseline, not a full external method

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **builtin** | Fast sanity-check baseline | `cell_type_key`, `species` | Small curated interaction list |
| **liana** | Best first rich Python-native backend | `cell_type_key`, `species` | Wrapper does not expose LIANA’s full filtering surface |
| **cellchat_r** | When users explicitly want CellChat-style analysis | `cell_type_key`, `species` | R backend and resource assumptions matter |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run cell-cell communication
  Method: liana
  Parameters: cell_type_key=cell_type, species=human
  Note: the grouping column is the most important scientific input for this analysis.
```

## Step 4: Method-Specific Tuning Rules

Tune in this order:
1. `cell_type_key`
2. `method`
3. `species`

Guidance:
- treat grouping quality as more important than backend switching
- use `builtin` as a quick baseline, then `liana` or `cellchat_r` if the user needs richer inference

Important warnings:
- do not expose LIANA `expr_prop`, `min_cells`, or CellChat internal model parameters as current public OmicsClaw knobs
- do not promise correct species-specific biology if the requested resource support is uncertain

## Step 5: What To Say After The Run

- If interactions are sparse: question label quality and species/resource compatibility first.
- If the built-in method and LIANA disagree: explain that the built-in method is intentionally lightweight.
- If users ask for pathway-level CellChat controls: explain that the current wrapper does not expose that full surface.

## Step 6: Explain Outputs Using Method-Correct Language

- describe interaction tables as ranked ligand-receptor hypotheses between label groups
- describe top plots as summaries of scored interactions, not direct causal proof
- describe method names explicitly because score semantics differ by backend

## Official References

- https://liana-py.readthedocs.io/en/latest/generated/liana.method.rank_aggregate.__call__.html
- https://liana-py.readthedocs.io/
- https://github.com/jinworks/CellChat

