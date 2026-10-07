# %% [markdown]
# Score PBMC lineage gene sets with the Python AUCell implementation.
# Reads pbmc3k_processed and uses its log-normalized raw snapshot.
# Calls sc-pathway-scoring: score_gene_sets, group_scores, score_distribution_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

pathways = load_skill('sc-pathway-scoring')
adata = load_demo('pbmc3k_processed').raw.to_adata()
gene_sets = {
    'B_cell': ['MS4A1', 'CD79A', 'CD79B', 'CD74', 'HLA-DRA'],
    'T_cell': ['CD3D', 'CD3E', 'CD3G', 'TRAC', 'IL7R'],
    'Myeloid': ['LYZ', 'S100A8', 'S100A9', 'FCN1', 'CTSS'],
}

# %%
scores = pathways.score_gene_sets(adata, gene_sets, method='aucell_py')
write_output(scores, 'tables/pathway_scores.csv')
write_output(pathways.group_scores(adata, scores, groupby='louvain'), 'tables/group_scores.csv')
write_output(pathways.score_distribution_figure(scores), 'figures/score_distribution.png')

# %%
assert scores.index.equals(adata.obs_names)
assert set(scores.columns) == set(gene_sets)
assert scores.max().max() > 0
assert scores.min().min() >= 0
