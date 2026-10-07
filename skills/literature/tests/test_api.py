import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def test_metadata_extraction_deduplicates_normalized_accessions_and_keeps_evidence():
    library = load_skill('literature')
    text = 'Human brain Visium data GSE123456, gse123456 and GSM1234567; resolution=0.8.'
    result = library.extract(text)
    assert result['accession'].tolist() == ['GSE123456', 'GSM1234567']
    info = library.run_info(result)
    assert info['organism'] == 'homo sapiens'
    assert info['technology'] == 'Visium'
    evidence = library.methodology(text)
    row = evidence.iloc[0]
    assert text[row.start:row.end] == row.quote == 'resolution=0.8'
    assert library.accession_figure(result).axes


def test_text_reader_is_explicit_and_missing_file_raises(tmp_path):
    library = load_skill('literature')
    path = tmp_path / 'paper.txt'
    path.write_text('GSE123456')
    assert library.read_document(path) == 'GSE123456'
    with pytest.raises(FileNotFoundError):
        library.read_document(tmp_path / 'missing.txt')


def test_fetch_failure_is_not_returned_as_paper_text(monkeypatch):
    import requests
    def fail(*args, **kwargs):
        raise requests.ConnectionError('offline')
    monkeypatch.setattr(requests, 'get', fail)
    with pytest.raises(requests.ConnectionError, match='offline'):
        load_skill('literature').fetch_text('https://example.org/paper')
