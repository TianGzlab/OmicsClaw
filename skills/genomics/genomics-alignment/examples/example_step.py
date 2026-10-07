# %% [markdown]
# A hand-worked synthetic fixture checks alignment summary values.
# %%
from pathlib import Path
import skills._sdk
from skills._sdk.notebook import load_skill, read_input, write_output

library = load_skill("genomics-alignment")
data_dir = Path(skills._sdk.__file__).resolve().parents[1] / "genomics/genomics-alignment/data"
source = next(data_dir.glob("example.*"))
data = read_input(str(source), reader=library.read_records)
result = library.analyze(data)
summary = library.run_info(result)["summary"]
assert summary["mapping_rate_pct"] == 75
write_output(result, "tables/alignment.csv")
write_output(library.distribution_figure(result), "figures/alignment.png")
