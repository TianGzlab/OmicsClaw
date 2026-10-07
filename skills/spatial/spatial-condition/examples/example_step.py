# %% [markdown]
# Compare six simulated samples; they are not independent biological measurements.

# %%
import matplotlib.pyplot as plt
import numpy as np
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill("spatial-condition")
adata = load_demo("spatial_synthetic")
adata.obs["leiden"] = adata.obs["domain_ground_truth"].astype(str)
adata.obs["sample_id"] = [f"sample_{i % 6}" for i in range(adata.n_obs)]
adata.obs["condition"] = np.where(np.arange(adata.n_obs) % 6 < 3, "control", "treated")
adata.layers["counts"] = adata.X.copy()

# %%
adata = library.compare_conditions(adata, method="wilcoxon")
table = library.results(adata)
assert library.run_info(adata)["n_samples"] == 6
assert not table.empty
assert table["n_samples_reference"].eq(3).all()
assert table["n_samples_other"].eq(3).all()
write_output(table, "tables/pseudobulk_de.csv")
write_output(adata, "intermediate/compared.h5ad")
figure = library.volcano_figure(adata)
write_output(figure, "figures/volcano.png")
plt.close(figure)
