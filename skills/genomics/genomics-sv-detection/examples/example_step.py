# %% [markdown]
# A hand-worked synthetic fixture checks sv-detection summary values.
# %%
from pathlib import Path
import skills._sdk
from skills._sdk.notebook import load_skill, read_input, write_output

library = load_skill("genomics-sv-detection")
data_dir = Path(skills._sdk.__file__).resolve().parents[1] / "genomics/genomics-sv-detection/data"
source = next(data_dir.glob("example.*"))
data = read_input(str(source), reader=library.read_records)
result = library.analyze(data)
summary = library.run_info(result)["summary"]
assert summary["n_tra"] == 1
write_output(result, "tables/sv_detection.csv")
write_output(library.distribution_figure(result), "figures/sv_detection.png")
