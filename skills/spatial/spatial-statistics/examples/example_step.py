"""Measure same-stripe enrichment in a synthetic spatial tissue."""
from skills._sdk.notebook import load_demo, load_skill, write_output

data = load_demo("spatial_synthetic")
data.obs["leiden"] = data.obs["domain_ground_truth"]
library = load_skill("spatial-statistics")
library.analyze(data, random_state=123)
scores = library.results_table(data, name="zscore_df")
assert all(scores.iloc[i, i] > 2 for i in range(3))
write_output(library.results_table(data), "tables/neighborhood_pairs.csv")
write_output(library.enrichment_figure(data), "figures/enrichment.png")
