# Parameters

Run `python skills/bulkrna/bulkrna-ppi-network/bulkrna_ppi_network.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) gives library defaults.

fetch_interactions explicitly queries STRING with a 0 to 1000 confidence threshold and returns 0 to 1 scores. analyze uses an unweighted graph and includes provided isolates. Hub scores combine normalized degree and betweenness. The CLI demo reads the fixed 364-edge STRING table described in data/README.md; it does not contact STRING.
