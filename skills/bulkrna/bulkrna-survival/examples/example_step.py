# %% [markdown]
# Synthetic survival data with explicit method and known checks.
# %%
import numpy as np
import pandas as pd
from skills._sdk.notebook import load_skill, write_output

library = load_skill("bulkrna-survival")
data = pd.DataFrame([range(8)], index=["G"], columns=[f"sample{i}" for i in range(8)])
clinical = pd.DataFrame({"sample": data.columns, "time": [1, 2, 3, 4, 2, 4, 6, 8], "event": [1] * 8})
result = library.analyze(data, clinical=clinical, backend="python")
assert result.gene.tolist() == ["G"]
assert result.hazard_ratio.iloc[0] == 0.5
assert library.run_info(result)["hazard_estimator"] == "events-per-person-time"
write_output(result, "tables/result.csv")
write_output(library.curve_figure(result, gene="G"), "figures/result.png")
