# %% [markdown]
# Synthetic protein-table example; these are not measured experimental results.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('proteomics-ptm')
data = library.demo_data(random_state=42)
result = library.classify_sites(data)
assert set(result['site_class']) == {'Class I','Class II','Class III'}
write_output(result, 'tables/ptm_sites.csv')
figure = library.class_figure(result)
write_output(figure, 'figures/class_figure.png')
