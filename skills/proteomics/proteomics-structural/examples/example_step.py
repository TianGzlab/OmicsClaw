# %% [markdown]
# Synthetic protein-table example; these are not measured experimental results.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('proteomics-structural')
data = library.demo_data(random_state=42)
result = library.analyse_crosslinks(data)
assert set(result['link_type']) == {'inter-protein','intra-protein'}
assert result['fdr'].max() <= .05
write_output(result, 'tables/crosslinks.csv')
figure = library.distance_figure(result)
write_output(figure, 'figures/distance_figure.png')
