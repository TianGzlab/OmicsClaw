# %% [markdown]
# Seeded synthetic example; results are not biological evidence.

# %%
from skills._sdk.notebook import load_skill, write_output
from skills.metabolomics._lib.demo import peak_detection
data = peak_detection()
library = load_skill('metabolomics-peak-detection')
result = library.detect_peaks(data)
assert len(result) > 0
write_output(result, 'tables/detected_peaks.csv')
figure = library.peaks_figure(result)
write_output(figure, 'figures/analysis.png')
