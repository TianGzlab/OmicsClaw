# %% [markdown]
# Synthetic protein-table example; these are not measured experimental results.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('proteomics-data-import')
data = library.demo_data(random_state=42)
result = library.standardize(data)
assert len(result) == 195 and 'Int_sample_1' in result
write_output(result, 'tables/proteins.csv')
figure = library.intensity_figure(result)
write_output(figure, 'figures/intensity_figure.png')
