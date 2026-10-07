"""Local literature extraction CLI and public-library parity."""


def register(Case, Skill):
    return {'literature': Skill('skills/literature/literature_parse.py', 'tests.parity.literature:api_literature', {'default': Case(('--demo',))})}


def api_literature(case):
    from skills._sdk.notebook import load_skill
    library = load_skill('literature')
    result = library.extract('We profiled human brain spatial transcriptomics with Visium and deposited the processed data in GEO under accession GSE123456.')
    info = library.run_info(result)
    return {'summary': {'method': 'metadata-extraction', 'gse_count': len(result[result['kind'] == 'gse']), 'organism': info['organism'], 'technology': info['technology']}}
