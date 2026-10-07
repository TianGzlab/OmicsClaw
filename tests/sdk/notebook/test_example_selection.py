"""CI modality jobs select domains, not skill-name spelling conventions."""
from tests.sdk.notebook.test_skill_examples import EXAMPLES, REPO


def test_remaining_job_contains_exactly_the_five_migrated_domains():
    selected = [parameter.values[0] for parameter in EXAMPLES
                if any(mark.name == 'skill_example_remaining' for mark in parameter.marks)]
    assert len(selected) == 41
    assert {path.relative_to(REPO / 'skills').parts[0] for path in selected} == {
        'bulkrna', 'genomics', 'proteomics', 'metabolomics', 'literature'}


def test_atac_example_stays_in_the_singlecell_job():
    parameter = next(p for p in EXAMPLES if p.values[0].parent.parent.name == 'scatac-preprocessing')
    assert not any(mark.name == 'skill_example_remaining' for mark in parameter.marks)
