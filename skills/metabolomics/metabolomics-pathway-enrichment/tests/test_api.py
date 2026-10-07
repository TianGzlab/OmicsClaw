import pytest
import json
import pandas as pd
import subprocess
import sys
from pathlib import Path
from skills._sdk.notebook import load_skill


def test_missing_reference_is_rejected():
    with pytest.raises(ValueError, match='explicit.*pathways'):
        load_skill('metabolomics-pathway-enrichment').enrich(['glucose', 'pyruvate', 'lactate'])


@pytest.mark.cli_subprocess
def test_real_cli_missing_reference_is_rejected(tmp_path):
    data = tmp_path / 'metabolites.csv'
    data.write_text('metabolite\nglucose\npyruvate\nlactate\n')
    script = Path(__file__).parents[1] / 'met_pathway.py'
    output = tmp_path / 'output'
    completed = subprocess.run([sys.executable, str(script), '--input', str(data), '--output', str(output)], capture_output=True, text=True)
    assert completed.returncode != 0
    assert '--pathway-file' in completed.stderr
    assert not (output / 'result.json').exists()


@pytest.mark.cli_subprocess
@pytest.mark.parametrize('demo', [False, True])
def test_cli_uses_explicit_reference_and_records_scope(tmp_path, demo):
    script = Path(__file__).parents[1] / 'met_pathway.py'
    output = tmp_path / 'output'
    arguments = ['--demo']
    if not demo:
        data = tmp_path / 'metabolites.csv'
        data.write_text('metabolite\na\nb\n')
        reference = tmp_path / 'pathways.json'
        reference.write_text(json.dumps({'selected': {'kegg_id': '', 'metabolites': ['a', 'b']},
                                        'other': {'kegg_id': '', 'metabolites': ['c', 'd']}}))
        arguments = ['--input', str(data), '--pathway-file', str(reference)]
    completed = subprocess.run([sys.executable, str(script), *arguments, '--output', str(output)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    envelope = json.loads((output / 'result.json').read_text())
    assert envelope['data']['run_info']['reference_scope'] == ('demo' if demo else 'provided')
    assert envelope['summary']['n_pathways_tested'] == (9 if demo else 2)
    if not demo:
        table = pd.read_csv(output / 'tables/pathway_enrichment.csv')
        assert table.loc[0, 'pvalue'] == pytest.approx(1 / 6)


def test_explicit_pathway_reference_has_known_hypergeometric_probability():
    library = load_skill('metabolomics-pathway-enrichment')
    pathways = {'selected': {'kegg_id': '', 'metabolites': ['a', 'b']}, 'other': {'kegg_id': '', 'metabolites': ['c', 'd']}}
    result = library.enrich(['a', 'b'], pathways=pathways)
    assert result.loc[0, 'pathway'] == 'selected'
    assert result.loc[0, 'pvalue'] == pytest.approx(1 / 6)
    assert library.run_info(result)['reference_scope'] == 'provided'
    assert library.enrichment_figure(result).axes


def test_unimplemented_pathway_method_is_rejected():
    with pytest.raises(ValueError, match='ora'):
        load_skill('metabolomics-pathway-enrichment').enrich(['glucose'], method='fella')


def test_no_overlap_retains_result_schema():
    library = load_skill('metabolomics-pathway-enrichment')
    result = library.enrich(['not_in_reference'], pathways=library.demo_pathways())
    assert result.empty and 'fdr' in result
