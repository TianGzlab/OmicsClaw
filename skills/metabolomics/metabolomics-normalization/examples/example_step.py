# %% [markdown]
# Seeded synthetic example; results are not biological evidence.

# %%
from skills._sdk.notebook import load_skill, write_output
from skills.metabolomics._lib.demo import normalization
data = normalization()
library = load_skill('metabolomics-normalization')
result = library.normalize(data)
assert len(result) > 0
write_output(result, 'tables/normalized.csv')
figure = library.distribution_figure(result)
write_output(figure, 'figures/analysis.png')
