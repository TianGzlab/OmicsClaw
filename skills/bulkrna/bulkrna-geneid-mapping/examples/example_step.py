# %% [markdown]
# Small human identifier fixture; the bundled reference has ten genes only.

# %%
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

library = load_skill('bulkrna-geneid-mapping')
counts = pd.DataFrame({'sample1': [2, 3, 7], 'sample2': [4, 6, 8]}, index=['ENSG00000141510.1', 'ENSG00000141510.2', 'ENSG00000012048'])
mapped = library.map_ids(counts)
assert mapped.loc['TP53', 'sample1'] == 5
assert mapped.loc['BRCA1', 'sample2'] == 8
write_output(mapped, 'tables/mapped_counts.csv')
write_output(library.mapping_table(mapped), 'tables/mapping_table.csv')
write_output(library.mapping_figure(mapped), 'figures/mapping.png')
