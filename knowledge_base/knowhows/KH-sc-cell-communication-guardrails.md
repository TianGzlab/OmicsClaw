---
doc_id: sc-cell-communication-guardrails
title: Single-Cell Communication Guardrails
doc_type: knowhow
critical_rule: MUST verify the cell-type labels and explain the selected communication backend plus species setting before running sc-cell-communication
domains: [singlecell]
related_skills: [sc-cell-communication]
phases: [before_run, on_warning, after_run]
search_terms: [cell communication, ligand receptor, LIANA, CellChat, NicheNet, species, 单细胞通讯, 配体受体, 调参]
priority: 1.0
source_urls:
  - https://liana-py.readthedocs.io/en/latest/generated/liana.method.rank_aggregate.__call__.html
  - https://github.com/jinworks/CellChat
  - https://github.com/saeyslab/nichenetr
---

# Single-Cell Communication Guardrails

- **Inspect first**: confirm that the chosen `cell_type_key` contains biologically interpretable labels rather than raw QC groups.
- **Standardize external inputs first**: when input provenance is unclear, recommend `sc-standardize-input` before communication analysis.
- **Key wrapper controls**: explain `method`, `cell_type_key`, and `species` before running.
- **Use method-correct language**: `builtin`, `liana`, and `cellchat_r` all depend on how cells are grouped; the grouping column is therefore the most important user-facing control in this wrapper.
- **Stop for missing grouping metadata**: do not run if `cell_type_key` is absent or still ambiguous; users must confirm which annotation / cluster column should define the interacting groups.
- **Do not invent unsupported knobs**: official LIANA and CellChat workflows expose extra filters such as expression cutoffs and permutation settings, but the current OmicsClaw wrapper does not expose them.
- **Do not overclaim species support**: if the ligand-receptor database coverage is uncertain for the requested species, say so.
- **Confirm identifier semantics for CellPhoneDB**: the `cellphonedb_counts_data` choice depends on the user’s gene IDs and should not be guessed silently.
- **Treat NicheNet as receiver-centric**: `nichenet_r` needs an explicit receiver cell type, sender cell types, and two conditions; do not describe it as the same kind of score as LIANA / CellPhoneDB.
- **Be honest about significance semantics**: the `builtin` backend leaves `pvalue` empty because it does not run a statistical significance test; do not describe its outputs as formal statistical significance.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-cell-communication.md`.
