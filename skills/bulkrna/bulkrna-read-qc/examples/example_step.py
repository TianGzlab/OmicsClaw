# %% [markdown]
# Synthetic demonstration; no measured experimental data are used.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('bulkrna-read-qc')
data = library.demo_data(random_state=42)
result = library.quality_control(data)
assert result.loc[0,'n_reads'] == 5000
assert result.loc[0,'mean_read_length'] == 150
assert result.loc[0,'q20_rate'] > result.loc[0,'q30_rate']
write_output(result.reset_index() if 'read-qc' == 'trajblend' else result, 'tables/qc_summary.csv')
write_output(library.quality_figure(result), 'figures/quality_figure.png')
