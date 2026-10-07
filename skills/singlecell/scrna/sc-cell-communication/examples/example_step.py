# %% [markdown]
# Rank curated ligand-receptor mean products across PBMC clusters.
# Reads pbmc3k_processed and uses its log-normalized raw snapshot.
# Calls sc-cell-communication: communicate, sender_receiver_summary, interaction_heatmap_figure.
# The builtin method does not test statistical significance.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

communication = load_skill('sc-cell-communication')
adata = load_demo('pbmc3k_processed').raw.to_adata()

# %%
table = communication.communicate(adata, cell_type_key='louvain')
write_output(table, 'tables/lr_interactions.csv')
write_output(communication.sender_receiver_summary(table), 'tables/sender_receiver.csv')
write_output(communication.interaction_heatmap_figure(table), 'figures/interaction_heatmap.png')

# %%
assert not table.empty
assert table.pvalue.isna().all()
assert (table.score > 0).all()
assert set(table.source).issubset(set(adata.obs['louvain'].astype(str)))
