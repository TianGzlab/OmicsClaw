# %% [markdown]
# Seeded synthetic example; results are not biological evidence.

# %%
from skills._sdk.notebook import load_skill, write_output
from skills.metabolomics._lib.demo import de
data = de()
library = load_skill('metabolomics-de')
result = library.differential_expression(data)
assert len(result) > 0
write_output(result, 'tables/differential_features.csv')
figure = library.pca_figure(data)
write_output(figure, 'figures/analysis.png')
