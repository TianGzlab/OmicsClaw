# %% [markdown]
# Synthetic coexpression data with explicit method and known checks.
# %%
import numpy as np
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

library = load_skill("bulkrna-coexpression")
rng = np.random.default_rng(9)
signals = rng.normal(size=(3, 20))
values = np.vstack([signal + rng.normal(0, 0.05, (20, 20)) for signal in signals])
data = pd.DataFrame(values + 10, index=[f"gene-{i}" for i in range(60)],
                    columns=[f"sample {i}" for i in range(20)])
result = library.analyze(data, power=6, min_module_size=10)
assert set(result.gene) == set(data.index)
assert library.run_info(result)["summary"]["soft_power"] == 6
assert library.run_info(result)["summary"]["n_modules"] >= 2
write_output(library.hub_genes(result), "tables/hubs.csv")
write_output(library.threshold_fit(result), "tables/threshold_fit.csv")
write_output(result, "tables/result.csv")
write_output(library.module_sizes_figure(result), "figures/result.png")
