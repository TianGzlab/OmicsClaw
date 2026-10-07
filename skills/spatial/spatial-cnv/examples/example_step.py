# %% [markdown]
# A synthetic chromosome exercises the CNV interface, not a tumor diagnosis.

# %%
import matplotlib.pyplot as plt
import numpy as np
import scanpy as sc
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill("spatial-cnv")
adata = load_demo("spatial_synthetic")
adata.var["chromosome"] = "chr1"
adata.var["start"] = np.arange(adata.n_vars) * 10000
adata.var["end"] = adata.var["start"] + 1000
sc.pp.normalize_total(adata, target_sum=10000)
sc.pp.log1p(adata)

# %%
library.cnv(adata, window_size=20, step=2, random_state=0)
table = library.scores(adata)
assert len(table) == adata.n_obs
assert np.isfinite(table["cnv_score"]).all()
write_output(table, "tables/cnv_scores.csv")
write_output(adata, "intermediate/cnv.h5ad")
figure = library.cnv_figure(adata)
write_output(figure, "figures/cnv.png")
plt.close(figure)
