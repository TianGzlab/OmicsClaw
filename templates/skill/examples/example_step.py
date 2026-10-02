# %% [markdown]
# Run REPLACE_SKILL_NAME's placeholder method on a small table and check the result.
# Reads nothing: the table is built below. In a real skill, load a registered
# demo dataset with load_demo(...) instead.
# Calls REPLACE_SKILL_NAME: run_method.

# %%
import pandas as pd

from skills._sdk.notebook import load_skill, write_output

library = load_skill("REPLACE_SKILL_NAME")
frame = pd.DataFrame({"feature": [f"feature_{i}" for i in range(5)], "value": [0.1, 0.4, -0.2, 1.3, 0.0]})

# %%
result = library.run_method(frame, method="default")
write_output(result, "tables/replace_me.csv")

# %%
assert list(result["method"].unique()) == ["default"]
assert len(result) == len(frame)
