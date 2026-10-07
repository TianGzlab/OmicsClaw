# Parameters

Run `python skills/metabolomics/metabolomics-pathway-enrichment/met_pathway.py --help` for CLI flags.

Real input requires `--pathway-file pathways.json`, a mapping such as `{"glycolysis": {"kegg_id": "map00010", "metabolites": ["glucose", "pyruvate"]}}`. The API requires the corresponding `pathways=` mapping. `--demo` supplies the illustrative reference explicitly; a pathway file, when supplied, takes precedence.
The generated API section in [SKILL.md](../SKILL.md) defines function defaults.

Matching is case-insensitive exact name equality, not substring matching. The background is the union of reference members. Hypergeometric survival probabilities and BH correction apply to pathways with at least one hit, matching the legacy CLI.
