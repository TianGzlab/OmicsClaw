# %% [markdown]
# Differential expression between known simulated spatial domains.

# %%
import matplotlib.pyplot as plt
import scanpy as sc
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill('spatial-de')
adata = load_demo('spatial_synthetic')
adata.layers['counts'] = adata.X.copy()
sc.pp.normalize_total(adata)
sc.pp.log1p(adata)

# %%
library.differential_expression(adata, groupby='domain_ground_truth',
                                group1='domain_0', group2='domain_1')
table = library.results(adata)
marker = table.set_index('names').loc['Gene_010']
assert marker['logfoldchanges'] > 1 and marker['pvals_adj'] < 0.01
write_output(table, 'tables/de_full.csv')
write_output(adata, 'intermediate/processed.h5ad')
figure = library.volcano_figure(adata)
write_output(figure, 'figures/volcano.png')
plt.close(figure)
