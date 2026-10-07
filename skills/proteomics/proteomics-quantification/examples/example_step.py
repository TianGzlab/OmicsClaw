# %% [markdown]
# Synthetic protein-table example; these are not measured experimental results.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('proteomics-quantification')
data = library.demo_data(random_state=42)
result = library.quantify(data)
assert result['abundance'].sum() > 0
write_output(result, 'tables/protein_abundance.csv')
figure = library.abundance_figure(result)
write_output(figure, 'figures/abundance_figure.png')
