"""Recover expression domains in the seeded synthetic tissue."""
import scanpy as sc
from sklearn.metrics import adjusted_rand_score
from skills._sdk.notebook import load_demo, load_skill, write_output

data = load_demo("spatial_synthetic")
sc.pp.normalize_total(data)
sc.pp.log1p(data)
sc.pp.pca(data, n_comps=20, random_state=0)
sc.pp.neighbors(data, random_state=0)
library = load_skill("spatial-domains")
library.identify(data, spatial_weight=0, resolution=0.5, random_state=0)
assert adjusted_rand_score(data.obs["domain_ground_truth"], data.obs["spatial_domain"]) > 0.95
write_output(library.domain_counts(data), "tables/domain_summary.csv")
write_output(library.domain_figure(data), "figures/domains.png")
