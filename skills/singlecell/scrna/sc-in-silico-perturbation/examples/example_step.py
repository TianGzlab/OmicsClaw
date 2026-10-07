# %% [markdown]
# Descriptive correlation edge-removal scores on PBMC expression.
# This does not simulate a causal knockout or test statistical significance.
# Calls sc-in-silico-perturbation: knockout_correlation, top_perturbed_genes, perturbed_genes_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

knockout = load_skill('sc-in-silico-perturbation')
adata = load_demo('pbmc3k_raw')

# %%
scores = knockout.knockout_correlation(adata, ko_gene='SPI1', n_top_genes=200)
write_output(scores, 'tables/correlation_scores.csv')
write_output(knockout.top_perturbed_genes(scores), 'tables/top_associations.csv')
write_output(knockout.perturbed_genes_figure(scores), 'figures/top_associations.png')

# %%
assert not scores.empty and 'SPI1' in set(scores['gene'])
assert scores['dr_score'].ge(0).all()
assert not {'p_value', 'p.adj', 'z_score'} & set(scores.columns)
