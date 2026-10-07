# %% [markdown]
# A hand-worked synthetic fixture checks qc summary values.
# %%
from pathlib import Path
import skills._sdk
from skills._sdk.notebook import load_skill, read_input, write_output

library = load_skill("genomics-qc")
data_dir = Path(skills._sdk.__file__).resolve().parents[1] / "genomics/genomics-qc/data"
source = next(data_dir.glob("example.*"))
data = read_input(str(source), reader=library.read_records)
result = library.analyze(data)
summary = library.run_info(result)["summary"]
assert summary["total_reads"] == 3
write_output(result, "tables/qc.csv")
write_output(library.distribution_figure(result), "figures/qc.png")
