# Parameters

Run `python skills/metabolomics/metabolomics-pathway-enrichment/met_pathway.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) defines function defaults.

Matching is case-insensitive exact name equality, not substring matching. The background is the union of reference members. Hypergeometric survival probabilities and BH correction apply to pathways with at least one hit, matching the legacy CLI.
