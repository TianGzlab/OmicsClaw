# Parameters

Run `python skills/metabolomics/metabolomics-peak-detection/peak_detect.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) defines function defaults.

scipy.signal.find_peaks uses prominence, optional height and a row-index distance after sorting by rt. Widths are measured at half prominence in row-index units.
