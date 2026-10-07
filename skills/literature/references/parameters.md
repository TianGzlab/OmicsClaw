# Parameters

Run `python skills/literature/literature_parse.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) gives library defaults.

extract performs local regex/keyword extraction only. methodology returns exact quotes and character spans for stated numeric parameters. read_document reads UTF-8 text or PDF, and fetch_text explicitly requests URL/DOI/PubMed text. Neither function downloads datasets; the CLI retains its optional GEO download workflow.
