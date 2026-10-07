# %% [markdown]
# Preprocess synthetic spatial counts with three known expression domains.
# These spots are simulated, not biological measurements.

# %%
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import adjusted_rand_score

from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill("spatial-preprocess")
source = load_demo("spatial_synthetic")
counts = source.X.copy()

# %%
adata = library.preprocess(source, n_top_hvg=150, n_pcs=15, random_state=0)
np.testing.assert_array_equal(source.X, counts)
np.testing.assert_array_equal(adata.layers["counts"], counts)
np.testing.assert_array_equal(adata.obsm["spatial"], source.obsm["spatial"])
score = adjusted_rand_score(adata.obs["domain_ground_truth"], adata.obs["leiden"])
assert score > 0.95, f"Known synthetic domains were not recovered: ARI={score:.3f}"

# %%
summary = library.cluster_summary(adata)
assert int(summary["n_cells"].sum()) == adata.n_obs
write_output(summary, "tables/cluster_summary.csv")
write_output(library.qc_metrics_table(adata), "tables/qc_metrics.csv")
write_output(library.pca_variance_table(adata), "tables/pca_variance.csv")
write_output(adata, "intermediate/processed.h5ad")
figure = library.spatial_figure(adata)
write_output(figure, "figures/spatial_leiden.png")
plt.close(figure)
