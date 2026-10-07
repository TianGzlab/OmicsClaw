# Methodology

The default hmdb lookup is a 15-entry demo. Pass reference= with name, neutral_mass, database_id and formula for local real-reference mass matching. No network lookup runs. The CLI has no reference-file flag.

`annotate` rejects other database labels without reference data. Each query can have multiple candidate rows in `tables/annotations.csv`; Unknown rows retain unmatched queries. Confidence labels describe ppm bins, not identification probability.
