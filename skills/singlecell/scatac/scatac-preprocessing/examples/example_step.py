# %% [markdown]
# Recover three planted peak-accessibility groups in synthetic ATAC counts.
# Reads atac_synthetic. Calls scatac-preprocessing: preprocess,
# cluster_summary, umap_figure. This checks implementation, not biological validity.

# %%
from sklearn.metrics import adjusted_rand_score
from skills._sdk.notebook import load_demo, load_skill, write_output

adata = load_demo("atac_synthetic")
library = load_skill("scatac-preprocessing")
result = library.preprocess(adata)
agreement = adjusted_rand_score(result.obs["demo_group"], result.obs["leiden"])
assert agreement > 0.9
assert result.n_obs < adata.n_obs
write_output(result, "intermediate/accessibility.h5ad")
write_output(library.cluster_summary(result), "tables/clusters.csv")
write_output(library.umap_figure(result), "figures/umap.png")
