# %% [markdown]
# A hand-worked synthetic fixture checks cnv-calling summary values.
# %%
from pathlib import Path
import skills._sdk
from skills._sdk.notebook import load_skill, read_input, write_output

library = load_skill("genomics-cnv-calling")
data_dir = Path(skills._sdk.__file__).resolve().parents[1] / "genomics/genomics-cnv-calling/data"
source = next(data_dir.glob("example.*"))
data = read_input(str(source), reader=library.read_bins)
result = library.analyze(data)
summary = library.run_info(result)["summary"]
assert summary["n_segments"] == 3
write_output(result, "tables/cnv_calling.csv")
write_output(library.copy_ratio_figure(result), "figures/cnv_calling.png")
