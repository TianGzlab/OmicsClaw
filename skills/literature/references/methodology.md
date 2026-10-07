# Methodology

extract performs local regex/keyword extraction only. methodology returns exact quotes and character spans for stated numeric parameters. read_document reads UTF-8 text or PDF, and fetch_text explicitly requests URL/DOI/PubMed text. Neither function downloads datasets; the CLI retains its optional GEO download workflow.

`extract` returns uppercase, deduplicated and sorted GEO identifiers. `methodology` never fills absent parameter defaults. `read_document` raises when pypdf is missing or input cannot be read. `fetch_text` propagates failures rather than treating an error message as paper text. Metadata labels remain heuristics, not validated study annotations.
