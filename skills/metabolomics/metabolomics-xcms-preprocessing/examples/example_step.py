# %% [markdown]
# This CLI produces a synthetic peak table only; no mzML processing runs.

# %%
import pandas as pd
from skills._sdk.notebook import run_cli, read_input, write_output

output = run_cli('metabolomics-xcms-preprocessing', '--demo', timeout=120)
table = read_input(output / 'tables/peak_table.csv', reader=pd.read_csv)
assert len(table) == 1200
assert all(table[f'sample_{i}'].ge(0).all() for i in range(1, 6))
write_output(table, 'tables/synthetic_peaks.csv')
