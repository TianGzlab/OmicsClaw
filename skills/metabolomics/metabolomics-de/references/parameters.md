# Parameters

Run `python skills/metabolomics/metabolomics-de/met_diff.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) defines function defaults.

Welch tests use raw supplied intensities, with BH FDR and a fixed CLI significance threshold of 0.05. PCA uses untransformed intensities and converts NaNs to zero.
