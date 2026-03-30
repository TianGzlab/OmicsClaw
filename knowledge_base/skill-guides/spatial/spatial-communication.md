---
doc_id: skill-guide-spatial-communication
title: OmicsClaw Skill Guide — Spatial Communication
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-cell-communication, spatial-communication, communication]
search_terms: [spatial communication, cell-cell communication, ligand receptor, LIANA, CellPhoneDB, FastCCC, CellChat, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Communication

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-communication` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:
- which communication backend is the best first pass for the current dataset
- which parameters matter first in OmicsClaw's current wrapper
- how to explain the result without pretending that all communication scores mean the same thing
- how to separate the standard Python gallery from later R-side visualization refinement

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:
- **Cell type column quality**:
  - does `obs[cell_type_key]` exist?
  - are labels biologically interpretable, or just rough clustering IDs?
- **Cell type count and imbalance**:
  - very small cell types interact strongly with `liana_min_cells` and `cellchat_min_cells`
- **Species**:
  - current wrapper only exposes `human` and `mouse`
  - `cellphonedb` and `fastccc` are human-only in current OmicsClaw
- **Expression representation**:
  - current `spatial-communication` uses log-normalized `adata.X`
  - do not describe scaled or z-scored matrices as acceptable CellPhoneDB input
- **Gene naming**:
  - CellPhoneDB and FastCCC are most natural when genes can be interpreted as HGNC symbols in the current wrapper

Important implementation notes in current OmicsClaw:
- All four backends consume `adata.X` in the current wrapper.
- LIANA automatically uses `adata.raw` when available, but this is expected to be the log-normalized full gene space rather than raw counts.
- FastCCC is now called through its real public API, not a nonexistent `fastccc.run(...)` wrapper.
- OmicsClaw standardizes all methods into a canonical LR table with `ligand`, `receptor`, `source`, `target`, `score`, and `pvalue`.
- CellChat exports extra pathway and centrality tables when the R run succeeds.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **LIANA** | Best default general-purpose first pass | `liana_resource=auto`, `liana_expr_prop=0.1`, `liana_min_cells=5`, `liana_n_perms=1000` | `score` and `pvalue` proxies in standardized output are not the same thing as CellPhoneDB permutation p-values |
| **CellPhoneDB** | User explicitly wants the official CellPhoneDB statistical method | `cellphonedb_threshold=0.1`, `cellphonedb_iterations=1000` | Human-only in current wrapper |
| **FastCCC** | Faster human communication screen without permutations | `fastccc_single_unit_summary=Mean`, `fastccc_complex_aggregation=Minimum`, `fastccc_lr_combination=Arithmetic`, `fastccc_min_percentile=0.1` | Human-only and score semantics differ from LIANA / CellPhoneDB |
| **CellChat** | Pathway-level communication, network role, and centrality analysis | `cellchat_prob_type=triMean`, `cellchat_min_cells=10` | Requires an R environment and should not be described as equivalent to permutation-based CellPhoneDB |

Practical default decision order:
1. If the user just says "run cell communication" with no method, start with **LIANA**.
2. Use **CellPhoneDB** when the user explicitly asks for CellPhoneDB or permutation-backed interaction statistics.
3. Use **FastCCC** when the user wants a faster first screen and the dataset is human.
4. Use **CellChat** when pathway-level signaling and network-role interpretation are the main goals.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial cell-cell communication
  Method: LIANA
  Parameters: cell_type_key=cell_type, species=human, liana_resource=auto, liana_expr_prop=0.1, liana_min_cells=5, liana_n_perms=1000
  Dataset: 12,842 spots across 9 cell types
  Note: LIANA is a strong first pass because it provides a general consensus-style communication screen before moving to method-specific follow-up runs.
```

## Step 4: Method-Specific Tuning Rules

### LIANA

Tune in this order:
1. `liana_resource`
2. `liana_expr_prop`
3. `liana_min_cells`
4. `liana_n_perms`

Guidance:
- Start with `liana_resource=auto`.
- For mouse data, `auto` resolves to `mouseconsensus`.
- Start with `liana_expr_prop=0.1`.
- Raise `liana_expr_prop` when extremely sparse genes are driving noisy candidate interactions.
- Lower `liana_expr_prop` when rare but plausible interactions are being excluded too aggressively.
- Start with `liana_min_cells=5`.
- Raise `liana_min_cells` when very tiny groups are generating unstable interactions.
- Increase `liana_n_perms` only when the user explicitly wants deeper LIANA permutation support.

Important warnings:
- Do not describe LIANA standardized `pvalue` as automatically identical to CellPhoneDB statistical p-values.
- LIANA is a strong screen, but it is not the same analysis story as direct CellPhoneDB or CellChat.

### CellPhoneDB

Tune in this order:
1. `cellphonedb_threshold`
2. `cellphonedb_iterations`

Guidance:
- Start with `cellphonedb_threshold=0.1`.
- Raise the threshold when you want to suppress interactions driven by very sparse expression.
- Lower the threshold when a rare-cell communication hypothesis is plausible and the user accepts more permissive inclusion.
- Start with `cellphonedb_iterations=1000`.
- Increase iterations when the user wants a more stable permutation estimate and accepts the runtime cost.

Important warnings:
- Current OmicsClaw CellPhoneDB wrapper is human-only.
- Do not call a scaled or z-scored matrix "good enough" for CellPhoneDB.

### FastCCC

Tune in this order:
1. `fastccc_single_unit_summary`
2. `fastccc_complex_aggregation`
3. `fastccc_lr_combination`
4. `fastccc_min_percentile`

Guidance:
- Start with `fastccc_single_unit_summary=Mean`.
- Use `Median`, `Q3`, or `Quantile_0.9` only when the user has a clear reason to emphasize a different within-cell-type summary behavior.
- Start with `fastccc_complex_aggregation=Minimum`.
- Consider `Average` when the user wants a less conservative complex summary.
- Start with `fastccc_lr_combination=Arithmetic`.
- Consider `Geometric` when the user wants stronger penalization when either ligand or receptor signal is weak.
- Start with `fastccc_min_percentile=0.1`.
- Raise `fastccc_min_percentile` to suppress interactions driven by very low prevalence expression.

Important warnings:
- In current OmicsClaw, FastCCC is human-only.
- Do not describe FastCCC score semantics as interchangeable with LIANA or CellPhoneDB.

### CellChat

Tune in this order:
1. `cellchat_prob_type`
2. `cellchat_min_cells`

Guidance:
- Start with `cellchat_prob_type=triMean`.
- Change `cellchat_prob_type` only when the user explicitly wants a different CellChat probability aggregation behavior.
- Start with `cellchat_min_cells=10`.
- Raise `cellchat_min_cells` when tiny groups are driving unstable communication calls.
- Lower `cellchat_min_cells` only when rare groups are biologically important and the user accepts more sensitivity.

Important warnings:
- CellChat is the right tool when the user cares about pathway-level communication and network roles, not just a ranked LR table.
- Do not say "CellChat p-values are the same as CellPhoneDB p-values"; the model and outputs differ.

## Step 5: Species Rules

- For **mouse** data, start with **LIANA** or **CellChat**.
- Do not offer **CellPhoneDB** or **FastCCC** as if mouse support already exists in the current wrapper.
- If the user insists on CellPhoneDB/FastCCC for mouse, explain that current OmicsClaw implementation does not support that combination yet.

## Step 6: What To Say After The Run

- If `n_significant` is very low: mention possible causes including mismatched cell type labels, sparse ligand/receptor expression, overly strict `cellphonedb_threshold`, or unsupported species-method expectations.
- If a small rare group dominates top interactions: suggest revisiting `liana_min_cells` or `cellchat_min_cells`.
- If LIANA returns broad but noisy rankings: suggest increasing `liana_expr_prop` or using a stricter downstream follow-up method.
- If CellPhoneDB runtime is too high: suggest keeping the threshold stable and reducing method switching before increasing permutation depth further.
- If FastCCC finds many weak interactions: suggest raising `fastccc_min_percentile`.
- If CellChat yields useful pathways but the user wants a more direct LR ranking comparison: suggest a LIANA or CellPhoneDB follow-up run.

## Step 7: Use The Visualization Layers Deliberately

Current OmicsClaw `spatial-communication` separates visualization into two
layers:

- **Python standard gallery**:
  - canonical analysis output
  - emitted under `figures/` with `figures/manifest.json`
  - should be the default artifact used in interactive analysis and routine
    reporting
- **R customization layer**:
  - optional refinement layer
  - should consume `figure_data/*.csv`
  - should not rerun communication inference just to restyle figures

Practical rule:

1. Use the Python gallery to confirm the scientific story and method behavior.
2. Use the R layer only when the user explicitly wants publication styling,
   panel composition, or custom aesthetics.
3. If an R script needs extra plotting inputs, export them from Python first
   instead of embedding scientific recomputation inside the visualization step.

## Step 8: Explain Results Using Method-Correct Language

When summarizing results to the user:
- For **LIANA**, describe the score as a consensus-style communication ranking score.
- For **CellPhoneDB**, describe the result as CellPhoneDB statistical communication output with method-specific thresholding and iterations.
- For **FastCCC**, describe the score as a FastCCC communication strength under the chosen summary / aggregation scheme.
- For **CellChat**, describe the outputs as CellChat communication probabilities plus pathway and centrality summaries.

Do **not** collapse all four methods into a generic "communication p-value"
story. In current OmicsClaw, they expose different statistical behaviors and
should be explained accordingly.
