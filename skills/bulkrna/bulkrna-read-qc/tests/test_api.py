import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_fastq_qc_uses_known_phred_and_gc_values():
    lib = load_skill('bulkrna-read-qc')
    reads = pd.DataFrame({'sequence':['ACGT','GGCC'],'quality':['IIII','5555']})
    result = lib.quality_control(reads)
    assert result.loc[0,'n_reads'] == 2
    assert result.loc[0,'mean_gc'] == 75.
    assert result.loc[0,'q20_rate'] == 100.
    assert result.loc[0,'q30_rate'] == 50.
    assert result.loc[0,'mean_quality'] == 30.


def test_reader_rejects_truncated_or_mismatched_fastq(tmp_path):
    lib = load_skill('bulkrna-read-qc')
    path = tmp_path/'bad.fastq'
    path.write_text('@one\nACGT\n+\nIII\n')
    with pytest.raises(ValueError,match='length'):
        lib.read_fastq(path)


def test_demo_records_have_matching_sequence_and_quality_lengths():
    reads = load_skill('bulkrna-read-qc').demo_data()
    assert (reads['sequence'].str.len() == reads['quality'].str.len()).all()
