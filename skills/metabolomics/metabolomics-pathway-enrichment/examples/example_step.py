# %% [markdown]
# Seeded synthetic example; results are not biological evidence.

# %%
from skills._sdk.notebook import load_skill, write_output
from skills.metabolomics._lib.demo import pathway_enrichment
data = pathway_enrichment()
library = load_skill('metabolomics-pathway-enrichment')
result = library.enrich(data['metabolite'], pathways=library.demo_pathways())
assert len(result) > 0
write_output(result, 'tables/pathway_enrichment.csv')
figure = library.enrichment_figure(result)
write_output(figure, 'figures/analysis.png')
