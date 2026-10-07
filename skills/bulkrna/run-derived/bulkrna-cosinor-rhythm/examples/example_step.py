# %%
import numpy as np
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

times = np.arange(0, 24, 4)
data = pd.DataFrame([10 + 3 * np.sin(2 * np.pi * times / 24)], index=['rhythm'],
                    columns=[f'T{t:02d}_R1' for t in times])
library = load_skill('bulkrna-cosinor-rhythm')
result = library.fit(data)
assert np.isclose(result.loc[0, 'amplitude'], 3)
write_output(result, 'tables/cosinor_results.csv')
write_output(library.rhythm_figure(result), 'figures/rhythm.png')
