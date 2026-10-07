# %% [markdown]
# Synthetic protein-table example; these are not measured experimental results.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('proteomics-de')
data = library.demo_data(random_state=42)
result = library.differential_abundance(data)
assert result['protein'].nunique() == 100
assert result.iloc[:25]['log2fc'].median() > result.iloc[25:]['log2fc'].median()
write_output(result, 'tables/differential_abundance.csv')
figure = library.volcano_figure(result)
write_output(figure, 'figures/volcano_figure.png')
