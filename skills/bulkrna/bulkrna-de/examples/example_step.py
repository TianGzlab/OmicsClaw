# %%
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

counts = pd.DataFrame({'ctrl_1': [10, 100], 'ctrl_2': [12, 120], 'ctrl_3': [11, 110],
                       'treat_1': [100, 10], 'treat_2': [120, 12], 'treat_3': [110, 11]}, index=['up', 'down'])
library = load_skill('bulkrna-de')
result = library.differential_expression(counts, method='ttest')
assert result.set_index('gene').loc['up', 'log2FoldChange'] > 3
write_output(result, 'tables/de.csv')
write_output(library.volcano_figure(result), 'figures/volcano.png')
