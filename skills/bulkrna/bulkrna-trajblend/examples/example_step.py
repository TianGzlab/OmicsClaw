# %% [markdown]
# Synthetic demonstration; no measured experimental data are used.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('bulkrna-trajblend')
data, reference, labels, pseudotime = library.demo_data(random_state=42)
result = library.map_trajectory(data, reference=reference, labels=labels, pseudotime=pseudotime)
assert result['pseudotime'].between(0,1).all()
assert library.fractions(result).sum(axis=1).between(.999999,1.000001).all()
write_output(result.reset_index() if 'trajblend' == 'trajblend' else result, 'tables/pseudotime_estimates.csv')
write_output(library.trajectory_figure(result), 'figures/trajectory_figure.png')
write_output(library.fractions(result).rename_axis('sample').reset_index(), 'tables/cell_fractions.csv')
