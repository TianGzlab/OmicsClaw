# %% [markdown]
# Seeded synthetic example; results are not biological evidence.

# %%
from skills._sdk.notebook import load_skill, write_output
from skills.metabolomics._lib.demo import annotation
data = annotation()
library = load_skill('metabolomics-annotation')
result = library.annotate(data)
assert len(result) > 0
write_output(result, 'tables/annotations.csv')
figure = library.mass_error_figure(result)
write_output(figure, 'figures/analysis.png')
