# %% [markdown]
# Recover a threefold change in a synthetic cell type using independent samples.
# Reads multisample_synthetic: four control and four treated samples.
# Calls sc-differential-abundance: test_abundance, composition, proportion_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

abundance = load_skill('sc-differential-abundance')
adata = load_demo('multisample_synthetic')

# %%
table = abundance.test_abundance(adata, method='simple')
counts, proportions = abundance.composition(adata, sample_key='sample',
    condition_key='condition', celltype_key='cell_type')
write_output(table, 'tables/abundance.csv')
write_output(counts, 'tables/sample_counts.csv')
write_output(abundance.proportion_figure(proportions), 'figures/sample_proportions.png')

# %%
enriched = table.set_index('cell_type').loc['Enriched']
assert enriched['significant']
assert enriched['log2fc_group_b_over_a'] > 1
assert counts.shape == (8, 3)
