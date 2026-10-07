# %% [markdown]
# Moran's I on simulated spatial stripes with known expression markers.

# %%
import matplotlib.pyplot as plt
import scanpy as sc
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill('spatial-genes')
adata = load_demo('spatial_synthetic')
adata.layers['counts'] = adata.X.copy()
sc.pp.normalize_total(adata)
sc.pp.log1p(adata)

# %%
library.spatial_genes(adata, random_state=0, n_perms=20)
table = library.results(adata)
markers = table.set_index('gene').loc[[f'Gene_{i:03d}' for i in range(90)]]
assert markers['I'].median() > 0.5
assert library.run_info(adata)['n_significant'] >= 60
write_output(table, 'tables/svg_results.csv')
write_output(adata, 'intermediate/processed.h5ad')
figure = library.ranking_figure(adata)
write_output(figure, 'figures/ranking.png')
plt.close(figure)
