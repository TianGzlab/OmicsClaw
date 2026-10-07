# Methodology

fetch_interactions explicitly queries STRING with a 0 to 1000 confidence threshold and returns 0 to 1 scores. analyze uses an unweighted graph and includes provided isolates. Hub scores combine normalized degree and betweenness. The CLI demo reads the fixed 364-edge STRING table described in data/README.md; it does not contact STRING.

`fetch_interactions` propagates HTTP/network errors and never substitutes demo edges. `analyze` defaults to the CLI neighborhood convention: degree includes external neighbors, closeness visits them, and betweenness is restricted to query nodes. Use induced=True to restrict all edges to the query set. `network_figure` draws query nodes only and uses seed 42 without changing the global random generator.
