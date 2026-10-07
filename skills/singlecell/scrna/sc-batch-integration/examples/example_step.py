# %% [markdown]
# Correct a fixed two-batch split of PBMC3k with Harmony.
# Reads pbmc3k_processed; the artificial batches only demonstrate the API.
# Calls sc-batch-integration: integrate, batch_sizes_table, batch_sizes_figure.

# %%
import numpy as np
import scanpy as sc
from skills._sdk.notebook import load_demo, load_skill, write_output

integration = load_skill("sc-batch-integration")
adata = load_demo("pbmc3k_processed").raw.to_adata()
adata.obs["batch"] = np.random.default_rng(0).choice(["a", "b"], adata.n_obs)
sc.pp.highly_variable_genes(adata, n_top_genes=2000)

# %%
adata = integration.integrate(adata, method="harmony", random_state=0)
write_output(integration.batch_sizes_table(adata), "tables/batch_sizes.csv")
write_output(integration.batch_sizes_figure(adata), "figures/batch_sizes.png")
write_output(adata, "intermediate/processed.h5ad")

# %%
assert adata.obsm["X_harmony"].shape == (adata.n_obs, 50)
assert np.isfinite(adata.obsm["X_harmony"]).all()
assert integration.run_info(adata)["summary"]["n_batches"] == 2
