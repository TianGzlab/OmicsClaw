# %% [markdown]
# Integrate simulated batches; this checks mechanics, not correction of real tissue.

# %%
import matplotlib.pyplot as plt
import numpy as np
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill("spatial-integrate")
preprocess = load_skill("spatial-preprocess")
adata = preprocess.preprocess(load_demo("spatial_synthetic"), n_top_hvg=150, n_pcs=15)
adata.obs["batch"] = [f"batch_{i % 3}" for i in range(adata.n_obs)]
expression = adata.X.copy()

# %%
adata = library.integrate(adata, random_state=0)
np.testing.assert_array_equal(adata.X, expression)
assert library.run_info(adata)["n_batches"] == 3
assert np.isfinite(adata.obsm["X_pca_harmony"]).all()
table = library.mixing_table(adata)
assert table["batch_entropy_after"].between(0, 1 + 1e-12).all()
write_output(table, "tables/batch_mixing.csv")
write_output(adata, "intermediate/integrated.h5ad")
figure = library.embedding_figure(adata)
write_output(figure, "figures/integration.png")
plt.close(figure)
