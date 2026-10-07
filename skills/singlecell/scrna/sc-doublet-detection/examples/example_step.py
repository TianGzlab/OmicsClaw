# %% [markdown]
# Annotate PBMC3k doublets with Scrublet without removing cells.
# Reads pbmc3k_raw. Calls sc-doublet-detection: detect_doublets and output helpers.

# %%
import numpy as np
from skills._sdk.notebook import load_demo, load_skill, write_output

doublets = load_skill("sc-doublet-detection")
adata = load_demo("pbmc3k_raw")
cells = adata.obs_names.copy()

# %%
doublets.detect_doublets(adata, expected_doublet_rate=0.06, random_state=0)
calls = doublets.doublet_calls_table(adata)
write_output(calls, "tables/doublet_calls.csv")
write_output(doublets.doublet_summary(adata), "tables/doublet_summary.csv")
write_output(doublets.doublet_score_figure(adata), "figures/doublet_scores.png")
write_output(adata, "intermediate/adata_doublets.h5ad")
assert adata.obs_names.equals(cells)
assert np.isfinite(adata.obs["doublet_score"]).all()
assert adata.obs["doublet_score"].max() > adata.obs["doublet_score"].min()
assert 0 < adata.obs["predicted_doublet"].sum() < adata.n_obs
