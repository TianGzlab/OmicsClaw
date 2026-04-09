---
doc_id: skill-guide-sc-cell-communication
title: OmicsClaw Skill Guide — SC Cell Communication
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-cell-communication]
search_terms: [cell communication, ligand receptor, LIANA, CellChat, NicheNet, groupby, species, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Cell Communication

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-cell-communication` skill. This guide explains the current wrapper surface
and does not imply the full LIANA, CellChat, CellPhoneDB, or NicheNet parameter set is exposed.

## Purpose

Use this guide when you need to decide:
- whether the current cell-type labels are good enough for communication analysis
- which backend is the best first pass
- which inputs must already be normalized vs raw count-like
- how to explain grouping and species settings correctly
- when receiver-vs-condition modeling makes NicheNet a better fit than a generic LR ranking

## Step 1: Inspect The Data First

Key properties to check:
- **Grouping column**:
  - `cell_type_key` must hold biologically meaningful labels
- **Species context**:
  - species affects ligand-receptor resource interpretation
- **Expression representation**:
  - LIANA / CellPhoneDB / CellChat need normalized expression in `adata.X`
  - NicheNet needs raw count-like input for receiver-side DE
- **Input provenance**:
  - if this is an external `.h5ad`, the wrapper will load it directly, but communication should still start only after preprocessing and labeling are biologically meaningful

Important implementation notes in current OmicsClaw:
- public methods are `builtin`, `liana`, `cellphonedb`, `cellchat_r`, and `nichenet_r`
- `cell_type_key` is the most important scientific parameter in the wrapper
- the built-in path is a lightweight OmicsClaw baseline, not a full external method
- `builtin` leaves `pvalue` empty because it is a heuristic ranking path rather than a formal significance test

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **builtin** | Fast sanity-check baseline | `cell_type_key`, `species` | Small curated interaction list and no formal significance testing |
| **liana** | Best first rich Python-native backend | `cell_type_key`, `species` | Wrapper does not expose LIANA’s full filtering surface |
| **cellphonedb** | Statistical LR screening with official database semantics | `cell_type_key`, `species`, `cellphonedb_counts_data`, `cellphonedb_threshold`, `cellphonedb_iterations` | Human-only in the current wrapper |
| **cellchat_r** | When users explicitly want CellChat-style analysis | `cell_type_key`, `species`, `cellchat_prob_type`, `cellchat_min_cells` | R backend and resource assumptions matter |
| **nichenet_r** | Receiver-centric ligand prioritization across two conditions | `cell_type_key`, `condition_key`, `receiver`, `senders`, `nichenet_top_ligands`, `nichenet_lfc_cutoff` | Human-only and score semantics differ from LR probability-style methods |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run cell-cell communication
  Method: liana
  Parameters: cell_type_key=cell_type, species=human
  Matrix note: this method will use normalized expression in adata.X
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
- use `nichenet_r` when the user already has a receiver cell type and a meaningful condition contrast
- if users only have cluster labels, say that communication on clusters is acceptable as a first pass, but final biological interpretation is stronger after annotation

Important warnings:
- do not expose LIANA `expr_prop`, `min_cells`, or CellChat internal model parameters as current public OmicsClaw knobs
- do not promise correct species-specific biology if the requested resource support is uncertain
- do not describe `builtin` `pvalue` values as formal hypothesis-test output; for this backend the field is intentionally left empty
- for `cellphonedb`, make the user confirm whether genes are HGNC symbols, Ensembl IDs, or plain gene names before trusting the default `cellphonedb_counts_data`
- for `cellchat_r`, if `adata.X` still looks count-like, stop and redirect to `sc-preprocessing` before pretending CellChat is using the expected normalized expression
- for `nichenet_r`, do not run unless `condition_key`, `condition_oi`, `condition_ref`, `receiver`, and `senders` are all explicitly grounded in `adata.obs`
- if CellPhoneDB or NicheNet resources are not cached locally, tell the user what will be downloaded before running

## Step 5: What To Say After The Run

- If interactions are sparse: question label quality and species/resource compatibility first.
- If the built-in method and LIANA disagree: explain that the built-in method is intentionally lightweight.
- If the run used `builtin`: explicitly say that `n_significant` is not a meaningful statistical count because the backend does not produce formal p values.
- If users ask for pathway-level CellChat controls: explain that the current wrapper does not expose that full surface.
- If the run used `nichenet_r`: explain that the main outputs are prioritized ligands and ligand-target links for the chosen receiver cell type.
- Good next steps are usually `sc-markers`, `sc-de`, or `sc-enrichment`, depending on whether the user wants marker validation, pairwise testing, or pathway interpretation.

## Step 6: Explain Outputs Using Method-Correct Language

- describe interaction tables as ranked ligand-receptor hypotheses between label groups
- describe top plots as summaries of scored interactions, not direct causal proof
- describe method names explicitly because score semantics differ by backend
- for `builtin`, describe the score as a grouped-expression heuristic rather than a statistical communication probability
- for `nichenet_r`, describe the score as ligand activity for the receiver cell type rather than a permutation-based interaction probability
- for `cellchat_r`, explain that pathway and centrality tables summarize network structure above the single LR-pair level

## Official References

- https://liana-py.readthedocs.io/en/latest/generated/liana.method.rank_aggregate.__call__.html
- https://liana-py.readthedocs.io/
- https://github.com/jinworks/CellChat
- https://github.com/saeyslab/nichenetr
