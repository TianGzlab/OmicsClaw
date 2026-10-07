"""Public diagnostic readers remove only their own record when requested."""

import json
import pytest

pytest.importorskip("scanpy")
import anndata as ad
import pandas as pd

from skills._sdk.notebook import load_skill


@pytest.mark.parametrize("skill,key", [
    ("sc-pathway-scoring", "omicsclaw_sc_pathway_scoring_run"),
    ("sc-gene-programs", "omicsclaw_sc_gene_programs_run"),
    ("sc-perturb", "sc_perturb_run_info"),
    ("sc-perturb-prep", "sc_perturb_prep_run_info"),
    ("sc-multi-count", "sc_multi_count_run"),
    ("scatac-preprocessing", "scatac_run"),
])
def test_run_info_can_remove_its_json_record(skill, key):
    data = ad.AnnData()
    data.uns[key] = json.dumps({"method": "recorded"})
    data.uns["unrelated"] = "keep me"
    api = load_skill(skill)
    assert api.run_info(data) == {"method": "recorded"}
    assert key in data.uns
    assert api.run_info(data, keep=False) == {"method": "recorded"}
    assert key not in data.uns and data.uns["unrelated"] == "keep me"
    assert api.run_info(data) == {}


def test_pathway_table_diagnostics_can_be_removed():
    data = pd.DataFrame({"pathway": [1.]})
    key = "omicsclaw_sc_pathway_scoring_run"
    data.attrs[key] = {"method": "score_genes_py"}
    api = load_skill("sc-pathway-scoring")
    assert api.run_info(data, keep=False) == {"method": "score_genes_py"}
    assert key not in data.attrs and api.run_info(data) == {}


@pytest.mark.parametrize("skill,key", [
    ("sc-drug-response", "run_info"),
    ("sc-in-silico-perturbation", "run_info"),
    ("sc-cell-communication", "omicsclaw_sc_cell_communication_run"),
    ("sc-differential-abundance", "omicsclaw_sc_differential_abundance_run"),
])
def test_result_table_diagnostics_follow_the_same_keep_contract(skill, key):
    data = pd.DataFrame()
    data.attrs[key] = {"method": "recorded"}
    api = load_skill(skill)
    assert api.run_info(data) == {"method": "recorded"}
    assert key in data.attrs
    assert api.run_info(data, keep=False) == {"method": "recorded"}
    assert key not in data.attrs and api.run_info(data) == {}
