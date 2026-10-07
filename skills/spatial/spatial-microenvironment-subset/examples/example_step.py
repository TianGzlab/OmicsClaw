"""Select a radius around one known stripe in the synthetic spatial demo."""
from skills._sdk.notebook import load_demo, load_skill, write_output

data = load_demo("spatial_synthetic")
library = load_skill("spatial-microenvironment-subset")
selected = library.subset(data, center_key="domain_ground_truth", center_values=["domain_0"], radius_native=1.5)
assert 0 < selected.n_obs < data.n_obs
assert library.run_info(selected)["n_center_observations"] == 60
write_output(library.selection_table(selected), "tables/selected_observations.csv")
write_output(selected, "intermediate/subset.h5ad")
write_output(library.selection_figure(selected), "figures/selection.png")
