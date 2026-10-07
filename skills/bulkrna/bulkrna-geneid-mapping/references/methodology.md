# Methodology

Local map_ids never queries the network. Its default reference contains ten human genes; it also supports reverse namespace mapping within that small reference. Pass a source/target DataFrame to override it. fetch_mapping explicitly sends identifiers to MyGene. The CLI queries MyGene only with --fetch-mygene.

`map_ids` strips Ensembl version suffixes, retains unmapped identifiers and resolves target collisions with sum, first or drop. Explicit mappings take priority. Non-human mapping without a reference raises an error. `run_info` identifies demo versus provided reference scope.
