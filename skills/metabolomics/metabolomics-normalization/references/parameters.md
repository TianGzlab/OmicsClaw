# Parameters

Run `python skills/metabolomics/metabolomics-normalization/metabolomics_normalization.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) defines function defaults.

Median and total scale each column to the median column median or sum. Quantile maps ranks to averaged sorted values. PQN uses a TIC-normalized reference to estimate quotients, then divides the original intensities. Log computes log2(x+1).
