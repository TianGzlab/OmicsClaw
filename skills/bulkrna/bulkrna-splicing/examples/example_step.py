# %%
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

events = pd.DataFrame({'gene': ['a', 'b', 'c'], 'event_type': ['SE', 'SE', 'RI'],
                      'delta_psi': [.3, -.1, -.4], 'padj': [.01, .01, .05]})
library = load_skill('bulkrna-splicing')
result = library.summarize(events)
assert library.significant_events(result)['gene'].tolist() == ['a']
write_output(result, 'tables/events.csv')
write_output(library.significant_events(result), 'tables/significant.csv')
write_output(library.volcano_figure(result), 'figures/events.png')
