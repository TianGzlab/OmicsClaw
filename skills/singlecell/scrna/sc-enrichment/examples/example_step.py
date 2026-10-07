# %% [markdown]
# Test the named PBMC demo signatures against marker rankings.
# Reads the log-normalised raw snapshot, not the scaled processed X matrix.
# Calls sc-enrichment: rank_groups, demo_gene_sets, ora, top_terms, top_terms_figure.

# %%
from skills._sdk.notebook import load_demo, load_skill, write_output

enrichment = load_skill("sc-enrichment")
adata = load_demo("pbmc3k_processed").raw.to_adata()

# %%
ranking = enrichment.rank_groups(adata, groupby="louvain")
sets = enrichment.demo_gene_sets()
results = enrichment.ora(ranking, sets, background=adata.var_names)
write_output(results, "tables/enrichment_full.csv")
write_output(enrichment.top_terms(results), "tables/enrichment_top_terms.csv")
write_output(enrichment.top_terms_figure(results), "figures/enrichment_top_terms.png")

# %%
assert not results.empty
assert set(results["engine"]) == {"hypergeometric_local"}
assert results["gene_count"].gt(0).all()
assert results["pvalue_adj"].between(0, 1).all()
