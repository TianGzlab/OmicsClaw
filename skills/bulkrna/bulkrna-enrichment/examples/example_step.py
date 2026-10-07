# %%
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

data = pd.DataFrame({'gene': ['a', 'b', 'c'], 'log2FoldChange': [3., 2., 0.],
                     'pvalue': [.001, .002, .8], 'padj': [.003, .004, .8]})
library = load_skill('bulkrna-enrichment')
result = library.enrich(data, gene_sets={'target': ['a', 'b'], 'background': list('abcdefghij')})
assert library.run_info(result)['background_genes'] == 10
# GSEApy reports overlapping genes in hash-dependent order.
result['genes'] = result['genes'].map(lambda value: ';'.join(sorted(value.split(';'))))
write_output(result, 'tables/enrichment.csv')
write_output(library.enrichment_figure(result), 'figures/enrichment.png')
