# %% [markdown]
# Align two simulated slices with unequal spot counts using PASTE on CPU.

# %%
import matplotlib.pyplot as plt
import numpy as np
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill("spatial-register")
adata = load_demo("spatial_synthetic")[:41, :40].copy()
adata.obs["slice"] = ["reference"] * 20 + ["source"] * 21
adata.obsm["spatial"] = adata.obsm["spatial"].astype(float)
adata.obsm["spatial"][20:] += [100, 30]
original = adata.obsm["spatial"].copy()

# %%
adata = library.register(adata, slice_key="slice", reference_slice="reference")
np.testing.assert_array_equal(adata.obsm["spatial"], original)
np.testing.assert_array_equal(adata.obsm["spatial_aligned"][:20], original[:20])
assert np.isfinite(adata.obsm["spatial_aligned"]).all()
table = library.shift_table(adata)
assert table["shift_distance"].iloc[20:].gt(0).all()
write_output(table, "tables/shifts.csv")
write_output(adata, "intermediate/registered.h5ad")
figure = library.registration_figure(adata)
write_output(figure, "figures/registration.png")
plt.close(figure)
