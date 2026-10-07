# %% [markdown]
# Synthetic protein-table example; these are not measured experimental results.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('proteomics-identification')
data = library.demo_data(random_state=42)
result = library.filter_identifications(data, n_spectra=1000)
assert result['qvalue'].max() <= .01
assert len(result) < len(data)
write_output(result, 'tables/peptides.csv')
figure = library.score_figure(result)
write_output(figure, 'figures/score_figure.png')
