# Outputs

The Python API returns in-memory objects and figures. It does not create a
report directory. Examples persist selected objects with `write_output`.

The standalone CLI writes `processed.h5ad`, `report.md` and `result.json`.
Its plots are under `figures/`; plot source tables are under `figure_data/`.
R exchange files live in temporary directories, not under `tables/`.

## Tables

All methods write these tables:

- `tables/lr_interactions.csv`: ligand, receptor, source, target, score, pvalue and pathway; LIANA also retains specificity_rank.
- `tables/top_interactions.csv`: the first 50 ranked interactions.
- `tables/sender_receiver_summary.csv`: mean score and interaction count per source-target pair.
- `tables/group_role_summary.csv`: summed outgoing and incoming scores per cell type.
- `tables/pathway_summary.csv`: mean pathway scores.

Additional nonempty backend tables may be written:

- CellChat: `cellchat_pathways.csv`, `cellchat_centrality.csv`, `cellchat_count_matrix.csv`, `cellchat_weight_matrix.csv`.
- CellPhoneDB: `cellphonedb_means.csv`, `cellphonedb_pvalues.csv`, `cellphonedb_significant_means.csv`.
- NicheNet: `nichenet_ligand_activities.csv`, `nichenet_ligand_target_links.csv`, `nichenet_ligand_receptors.csv` when returned.

Raw backend input H5AD/metadata and intermediate R output are temporary,
not promised report files. Figure availability depends on the backend
tables; optional R-enhanced plots go under `figures/r_enhanced/`.

## Significance

builtin and NicheNet do not supply p-values in the shared LR table.
LIANA's specificity_rank is a rank, not a p-value: pvalue is NaN and
n_significant is zero. CellPhoneDB's p-values come from permutations,
with debug_seed=0 by default. Read `run_info(table)` or CLI
`result.json["summary"]` for backend and significance semantics.
