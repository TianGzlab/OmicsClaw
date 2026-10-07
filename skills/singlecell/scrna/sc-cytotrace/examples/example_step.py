# %% [markdown]
# Demonstrate a relative complexity score on PBMC3k, not a validated differentiation trajectory.
# The processed dataset's raw snapshot contains unscaled log-normalized expression.
# Reads pbmc3k_processed. Calls sc-cytotrace: cytotrace, potency_table, potency_figure.

# %%
import numpy as np
import scanpy as sc
from skills._sdk.notebook import load_demo, load_skill, write_output

potency = load_skill("sc-cytotrace")
adata = load_demo("pbmc3k_processed").raw.to_adata()
sc.pp.pca(adata, n_comps=30, random_state=0)

# %%
potency.cytotrace(adata, n_neighbors=30)
write_output(potency.potency_table(adata), "tables/potency.csv")
write_output(potency.potency_figure(adata), "figures/potency_scores.png")
write_output(adata, "intermediate/adata_potency.h5ad")
assert np.isfinite(adata.obs["cytotrace_score"]).all()
assert adata.obs["cytotrace_score"].between(0, 1).all()
assert adata.obs["cytotrace_gene_count"].nunique() > 1
