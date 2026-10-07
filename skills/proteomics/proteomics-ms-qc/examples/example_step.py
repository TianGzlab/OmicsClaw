# %% [markdown]
# Synthetic protein-table example; these are not measured experimental results.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('proteomics-ms-qc')
data = library.demo_data(random_state=42)
result = library.quality_control(data)
assert result.loc[0,'n_proteins'] == 100
assert 0 < result.loc[0,'missing_rate'] < 100
write_output(result, 'tables/qc_metrics.csv')
figure = library.completeness_figure(result)
write_output(figure, 'figures/completeness_figure.png')
