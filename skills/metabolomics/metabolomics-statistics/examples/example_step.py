# %% [markdown]
# Seeded synthetic example; results are not biological evidence.

# %%
from skills._sdk.notebook import load_skill, write_output
from skills.metabolomics._lib.demo import statistics
data, first, second = statistics()
library = load_skill('metabolomics-statistics')
result = library.test_groups(data, group1_cols=first, group2_cols=second)
assert len(result) > 0
write_output(result, 'tables/statistics.csv')
figure = library.volcano_figure(result)
write_output(figure, 'figures/analysis.png')
