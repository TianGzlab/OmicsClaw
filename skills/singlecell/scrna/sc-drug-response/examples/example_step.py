# %% [markdown]
# Summarize drug-associated gene expression by annotated PBMC cell type.
# The averages are not sensitivity predictions or treatment recommendations.
# Calls sc-drug-response: score_drug_targets, top_drugs, top_drugs_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

drug = load_skill('sc-drug-response')
adata = load_demo('pbmc3k_processed').raw.to_adata()

# %%
scores = drug.score_drug_targets(adata, cluster_key='louvain')
write_output(scores, 'tables/mean_target_expression.csv')
write_output(drug.top_drugs(scores), 'tables/top_gene_sets.csv')
write_output(drug.top_drugs_figure(scores), 'figures/top_gene_sets.png')

# %%
assert not scores.empty
assert 'mean_target_expression' in scores and 'Score' not in scores
assert scores['TargetGenes'].gt(0).all()
assert scores['Cluster'].nunique() == adata.obs['louvain'].nunique()
