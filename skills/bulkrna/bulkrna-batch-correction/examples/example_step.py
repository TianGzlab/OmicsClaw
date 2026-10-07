# %% [markdown]
# Synthetic batch-correction data with explicit method and known checks.
# %%
import numpy as np
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

library = load_skill("bulkrna-batch-correction")
rng = np.random.default_rng(7)
data = pd.DataFrame(rng.normal(20, 1, (30, 8)), index=[f"gene{i}" for i in range(30)],
                    columns=[f"sample{i}" for i in range(8)])
data.iloc[:, 4:] += 10
batches = pd.DataFrame({"sample": data.columns, "batch": ["a"] * 4 + ["b"] * 4})
result = library.correct(data, batches=batches, backend="python")
assert library.run_info(result)["summary"]["n_batches"] == 2
assert library.run_info(result)["executed_method"] == "python-parametric"
assert np.isfinite(result.to_numpy()).all()
write_output(result, "tables/result.csv")
write_output(library.pca_figure(result, batches=batches), "figures/result.png")
