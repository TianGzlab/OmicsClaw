# STRING demo interactions

`demo_string_edges.csv` contains the 364 interaction rows exported by the
unmodified CLI at commit `f97f38c1` on 2026-10-07. Its query used the 30 demo
genes, human taxon 9606 and required score 400 at
`https://string-db.org/api/tsv/network`.

This is the old CLI's edge table, not the raw HTTP response. The CLI selected
preferredName_A, preferredName_B and score, renamed the first two columns and
filtered score >= 0.4; no centrality values were used to construct this table.
The public-interface tests separately check known centralities on a three-node
chain with an isolated node. Demo runs use this fixed reference offline.
