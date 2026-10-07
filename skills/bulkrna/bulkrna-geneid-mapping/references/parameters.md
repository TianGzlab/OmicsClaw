# Parameters

Run `python skills/bulkrna/bulkrna-geneid-mapping/bulkrna_geneid_mapping.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) gives library defaults.

Local map_ids never queries the network. Its default reference contains ten human genes; it also supports reverse namespace mapping within that small reference. Pass a source/target DataFrame to override it. fetch_mapping explicitly sends identifiers to MyGene. The CLI queries MyGene only with --fetch-mygene.
