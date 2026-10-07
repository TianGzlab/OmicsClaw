import pytest
from skills._sdk.notebook import load_skill


def test_star_counts_have_known_mapping_rates():
    text = 'Number of input reads | 100\nUniquely mapped reads number | 80\nNumber of reads mapped to multiple loci | 5\n'
    lib = load_skill('bulkrna-read-alignment')
    result = lib.summarize(text)
    assert result.loc[0,'unique_rate'] == 80.
    assert result.loc[0,'unmapped'] == 15
    assert lib.run_info(result)['quality']['overall'] == 'GOOD'


def test_salmon_total_mapping_is_not_claimed_as_unique_mapping():
    result = load_skill('bulkrna-read-alignment').summarize('{"num_processed":100,"num_mapped":90}',method='salmon')
    assert result.loc[0,'mapped_rate'] == 90.
    assert 'unique_rate' not in result


def test_unrecognized_logs_fail_instead_of_reporting_zero_reads():
    with pytest.raises(ValueError,match='reads'):
        load_skill('bulkrna-read-alignment').summarize('not an alignment log')
