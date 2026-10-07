# Parameters

Run `python skills/metabolomics/metabolomics-quantification/met_quantify.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) defines function defaults.

Min imputation uses half the global positive minimum, median uses each column positive median, and KNN uses neighbouring feature rows with up to five neighbours. TIC scales column sums to their median; median scales column medians; log computes log2(x+1).
