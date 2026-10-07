# %% [markdown]
# LIANA on measured PBMC expression. Coordinates below are simulated solely
# for spatial plotting; this example does not claim measured tissue interactions.

# %%
import matplotlib.pyplot as plt
import numpy as np
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill('spatial-communication')
adata = load_demo('pbmc3k_processed').raw.to_adata()
keep = adata.obs.groupby('louvain', observed=True).head(30).index
adata = adata[keep].copy()
adata.obsm['spatial'] = np.column_stack((np.arange(adata.n_obs) % 20,
                                       np.arange(adata.n_obs) // 20)).astype(float)
adata.uns['synthetic_coordinates'] = True

# %%
library.communicate(adata, cell_type_key='louvain', n_perms=10, random_state=1337)
table = library.interactions(adata)
assert not table.empty
assert table['score'].between(0, 1).all()
assert table['pvalue'].dropna().between(0, 1).all()
assert set(table['source']).issubset(adata.obs['louvain'])
write_output(table, 'tables/lr_interactions.csv')
write_output(adata, 'intermediate/processed.h5ad')
figure = library.roles_figure(adata)
write_output(figure, 'figures/signaling_roles.png')
plt.close(figure)
