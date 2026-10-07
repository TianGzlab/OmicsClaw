# %% [markdown]
# Synthetic demonstration; no measured experimental data are used.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('bulkrna-read-alignment')
data = library.demo_data(random_state=42)
result = library.summarize(data)
assert result.loc[0,'total_reads'] == 30000000
assert result.loc[0,'unique_rate'] > 80
write_output(result.reset_index() if 'read-alignment' == 'trajblend' else result, 'tables/alignment_stats.csv')
write_output(library.mapping_figure(result), 'figures/mapping_figure.png')
