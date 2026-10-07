"""Deconvolve known synthetic stripes against an explicit synthetic reference."""
import numpy as np
from skills._sdk.notebook import load_demo, load_skill, write_output

data = load_demo("spatial_synthetic")
reference = data.copy()
reference.obs["cell_type"] = reference.obs["domain_ground_truth"]
library = load_skill("spatial-deconv")
# The small coordinate grid needs less regularization than the CLI's tissue default.
library.deconvolve(data, reference=reference, method="flashdeconv", sketch_dim=64,
                   n_hvg=150, lambda_spatial=10, random_state=0)
table = library.proportions(data)
assert (table.idxmax(axis=1) == data.obs["domain_ground_truth"].astype(str)).mean() > 0.9
np.testing.assert_allclose(table.sum(axis=1), 1, atol=1e-5)
write_output(table, "tables/proportions.csv")
write_output(library.proportions_figure(data), "figures/mean_proportions.png")
