# Parameters

Run `python skills/metabolomics/metabolomics-annotation/metabolomics_annotation.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) defines function defaults.

Pass `reference=` with name, neutral_mass, database_id and formula for local reference mass matching. Real CLI input requires `--reference-file reference.csv`. No network lookup runs; `database` labels the supplied reference. `demo_reference()` or CLI `--demo` explicitly selects the 15-entry example reference.
