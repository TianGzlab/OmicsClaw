# %% [markdown]
# Synthetic protein-table example; these are not measured experimental results.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('proteomics-enrichment')
data = library.demo_data(random_state=42)
result = library.enrich(data['protein_id'].tolist(), pathway_db=library.demo_pathways())
assert len(result) == 8
assert result['overlap_count'].max() >= 3
write_output(result, 'tables/enrichment_results.csv')
figure = library.enrichment_figure(result)
write_output(figure, 'figures/enrichment_figure.png')
