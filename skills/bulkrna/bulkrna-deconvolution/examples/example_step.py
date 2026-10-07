# %%
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

counts = pd.DataFrame({'sample': [3., 1.]}, index=['a', 'b'])
signature = pd.DataFrame({'A': [1., 0.], 'B': [0., 1.]}, index=['a', 'b'])
library = load_skill('bulkrna-deconvolution')
result = library.deconvolve(counts, signature=signature)
assert result.loc['sample'].tolist() == [.75, .25]
write_output(result, 'tables/proportions.csv')
write_output(library.proportions_figure(result), 'figures/proportions.png')
