# %%
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

counts = pd.DataFrame({'ctrl_1': [1, 3, 0], 'treat_1': [2, 6, 0]}, index=['a', 'b', 'c'])
library = load_skill('bulkrna-qc')
result = library.assess(counts)
assert result['total_counts'].tolist() == [4, 8]
write_output(result, 'tables/sample_stats.csv')
write_output(library.normalized_counts(result), 'tables/cpm.csv')
write_output(library.library_figure(result), 'figures/libraries.png')
