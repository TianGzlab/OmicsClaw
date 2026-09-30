# Literature — Skill Index

> The skill list below is derived from each skill's `SKILL.md` frontmatter
> and is checked by `tests/skills/test_domain_index_is_current.py`.
> Regenerate it with
> `OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py`.
> The prose above the list is written by hand.

**Domain key:** `literature`

**Skill count:** 1

**Primary data types:** pdf, txt, doi, url

Scientific literature parsing for PDFs, URLs, DOIs, PubMed IDs, GEO accession extraction, and dataset metadata handoff.

## Skills

- `literature` — Load when extracting GEO accessions, dataset metadata, and downloadable references from a scientific paper (PDF / URL / DOI / PubMed ID / raw text) for downstream omics analysis. Skip when the dataset is already in hand; the paper names no dataset to fetch.
  triggers: parse paper, literature, GEO accession, download dataset, PDF extract, PubMed, DOI
